import colorsys
import numpy as np
import cairo
from overview import Overview
from collections import namedtuple

_Colors = namedtuple('_Colors', 'grid main fore')


class Waveform(object):

    def __init__(self, sound):
        self._sound = sound
        self._overview = Overview(sound)
        hue = 212.0 / 365.0
        gridcolor = (0.2, 0.2, 0.2)
        maincolor = colorsys.hls_to_rgb(hue, 0.5, 1.0)
        forecolor = colorsys.hls_to_rgb(hue, 0.75, 1.0)
        self._colors = _Colors(gridcolor, maincolor, forecolor)

    def set(self, start, width, density):
        self._view = (int(start), int(width), float(density))
        self._density = density

    def draw(self, context, width, height):
        data = self._overview(*self._view)
        numchan = len(data)
        if numchan > 1:
            height /= numchan
        context.save()
        for channel in data:
            self.draw_channel(channel, context, width, height)
            context.translate(0, height)
        context.restore()

    def draw_channel(self, data, context, width, height):
        self._draw_origin(context, width, height)
        start, width, density = self._view
        if density < 128:
            alpha = max(0.0, (density - 32.0) / 96.0)
            alpha = 1.0 - (alpha * alpha)
            self._draw_fill(data, context, width, height, alpha)
        if density > 8:
            alpha = min(1.0, (density - 8.0) / 96.0)
            self._draw_gradient(data, context, width, height, alpha)
        if density < 8:
            self._draw_line(data, context, width, height)

    def _draw_origin(self, context, width, height):
        # Line at zero
        context.set_line_width(1)
        context.set_source_rgb(*self._colors.grid)
        context.move_to(0, height/2)
        context.line_to(width, height/2)
        context.stroke()

    def _draw_line(self, data, context, width, height):
        # Draw a stroke along the mean, ensuring that the waveform stays visible
        # even when the limits are very close together.
        context.save()
        height /= 2
        context.translate(0, height)
        context.scale(1.0, -1.0)
        context.set_source_rgb(*self._colors.main)
        context.move_to(0, data[0].mean * height)
        for i in range(1, len(data)):
            context.line_to(i, data[i].mean * height)
        context.stroke()
        context.restore()

    def _draw_fill(self, data, context, width, height, alpha):
        # Draw the outline of the waveform; fill the shape between its limits.
        context.save()
        height /= 2
        context.translate(0, height)
        context.scale(1.0, -1.0)
        r, g, b = self._colors.main
        context.set_source_rgba(r, g, b, alpha)
        context.move_to(0, data[0].min * height)
        for i in range(1, len(data)):
            context.line_to(i, data[i].min * height - 0.5)
        for i in range(0, len(data)-1):
            context.line_to(width - i, data[-i].max * height + 0.5)
        context.close_path()
        context.fill()
        context.restore()

    def _draw_gradient(self, data, context, width, height, alpha):
        ypix, xpix = np.mgrid[:height, :width]
        yidx = 1 - (ypix.astype(np.float) / (float(height)/2))

        iota = np.fromiter((0.000001 for c in data), dtype=np.float)
        mins = np.fromiter((c.min for c in data), dtype=np.float)
        maxs = np.fromiter((c.max for c in data), dtype=np.float)
        avgs = np.fromiter((c.mean for c in data), dtype=np.float)
        stds = np.fromiter((c.std for c in data), dtype=np.float)
        lopks = avgs - mins
        hipks = maxs - avgs
        peaks = (lopks * (lopks >= hipks)) + (hipks * (hipks > lopks))
        crests = peaks / (stds + iota)

        ymin = np.tile(mins, (height, 1))
        ymax = np.tile(maxs, (height, 1))
        yavg = np.tile(avgs, (height, 1))
        ystd = np.tile(stds, (height, 1))
        ypeak = np.tile(peaks, (height, 1))
        ylostd = yavg - ystd
        yhistd = yavg + ystd
        ycrest = np.tile(crests, (height, 1))

        def paint(mask, color):
            mask = np.asarray(mask * 255, dtype=np.uint8)
            fmt = cairo.FORMAT_A8
            stride = cairo.ImageSurface.format_stride_for_width(fmt, width)
            if stride > width:
                mask = np.pad(mask, ((0, 0), (0, stride-width)), 'constant')
            img = cairo.ImageSurface.create_for_data(mask, fmt, width, height)
            r, g, b = color
            context.set_source_rgba(r, g, b, alpha)
            context.mask_surface(img)

        ramp_lo = (yidx - ymin) / (ylostd - ymin + iota)
        ramp_lo = np.clip(ramp_lo, 0, 1)
        ramp_lo *= (yidx >= ymin)
        ramp_hi = (ymax - yidx) / (ymax - yhistd + iota)
        ramp_hi = np.clip(ramp_hi, 0, 1)
        ramp_hi *= (yidx <= ymax)
        mask = ramp_hi * ramp_lo
        # do a little bit of horizontal anti-aliasing
        mask[:, 1:-1] += mask[:, :-2] * 0.18 + mask[:, 2:] * 0.18
        mask /= 1.36
        # power curve
        mask = np.sqrt(mask)
        paint(mask, self._colors.main)

        ramp_lo = np.tanh((yidx - ylostd) / (ylostd - ymin + iota) * np.pi)
        ramp_lo = (ramp_lo + 1.0) / 2.0
        ramp_lo *= (yidx > ymin)
        ramp_hi = np.tanh((yhistd - yidx) / (ymax - yhistd + iota) * np.pi)
        ramp_hi = (ramp_hi + 1.0) / 2.0
        ramp_hi *= (yidx < ymax)
        mask = (ramp_hi * ramp_lo) ** ycrest
        # the body highlighting is less meaningful at lower zoom levels
        mask *= 1.0 - (1.0 / np.log(self._density))
        paint(mask, self._colors.fore)
