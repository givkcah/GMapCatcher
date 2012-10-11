# -*- coding: utf-8 -*-
## @package gmapcatcher.widgets.widDrawingArea
# DrawingArea widget used to display the map

import gtk
import pango
import math
import gmapcatcher.mapUtils as mapUtils
from gmapcatcher.mapConst import *
from threading import Timer, Thread, Event
import copy
import time

ternary = lambda a, b, c: (b, c)[not a]


## This widget is where the map is drawn
class DrawingArea(gtk.DrawingArea):
    center = ((0, 0), (128, 128))
    draging_start = (0, 0)
    markerThread = None
    isPencil = False

    def __init__(self):
        super(DrawingArea, self).__init__()

        self.visualdl_gc = False
        self.scale_gc = False
        self.arrow_gc = False
        self.track_gc = False
        self.gps_track_gc = False

        self.trackThreadInst = None
        self.trackTimer = None
        self.gpsTrackInst = None

        self.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.connect('button-press-event', self.da_button_press)

        self.add_events(gtk.gdk.BUTTON_RELEASE_MASK)
        self.connect('button-release-event', self.da_button_release)

    def stop(self):
        if self.trackThreadInst:
            self.trackThreadInst.stop()
        if self.gpsTrackInst:
            self.gpsTrackInst.stop()

    ## Change the mouse cursor over the drawing_area
    def da_set_cursor(self, dCursor=gtk.gdk.HAND1):
        cursor = gtk.gdk.Cursor(dCursor)
        self.window.set_cursor(cursor)
        self.isPencil = (dCursor == gtk.gdk.PENCIL)

    ## Handles left (press click) event in the drawing_area
    def da_button_press(self, w, event):
        if (event.button == 1):
            self.draging_start = (event.x, event.y)
            if not self.isPencil:
                self.da_set_cursor(gtk.gdk.FLEUR)

    ## Handles left (release click) event in the drawing_area
    def da_button_release(self, w, event):
        if (event.button == 1):
            if not self.isPencil:
                self.da_set_cursor()

    ## Jumps in the drawing_area
    def da_jump(self, intDirection, zoom, doBigJump=False):
        # Left  = 1  Up   = 2
        # Right = 3  Down = 4
        intJump = 10
        if doBigJump:
            intJump = intJump * 10

        self.draging_start = (intJump * (intDirection == 3),
                              intJump * (intDirection == 4))
        self.da_move(intJump * (intDirection == 1),
                     intJump * (intDirection == 2), zoom)

    ## Move the drawing_area
    def da_move(self, x, y, zoom):
        rect = self.get_allocation()
        if (0 <= x <= rect.width) and (0 <= y <= rect.height):
            offset = (self.center[1][0] + (self.draging_start[0] - x),
                      self.center[1][1] + (self.draging_start[1] - y))
            self.center = mapUtils.tile_adjustEx(zoom, self.center[0], offset)
            self.draging_start = (x, y)
            self.repaint()

    ## Scale in the drawing area (zoom in or out)
    def do_scale(self, zoom, current_zoom_level, doForce, dPointer):
        if (zoom == current_zoom_level) and not doForce:
            return

        rect = self.get_allocation()
        da_center = (rect.width // 2, rect.height // 2)
        if dPointer:
            fix_tile, fix_offset = mapUtils.pointer_to_tile(
                rect, dPointer, self.center, current_zoom_level
            )
        else:
            fix_tile, fix_offset = self.center

        scala = 2 ** (current_zoom_level - zoom)
        x = int((fix_tile[0] * TILES_WIDTH + fix_offset[0]) * scala)
        y = int((fix_tile[1] * TILES_HEIGHT + fix_offset[1]) * scala)
        if dPointer and not doForce:
            x = x - (dPointer[0] - da_center[0])
            y = y - (dPointer[1] - da_center[1])

        self.center = (x / TILES_WIDTH, y / TILES_HEIGHT), \
                      (x % TILES_WIDTH, y % TILES_HEIGHT)
        self.repaint()

    ## Repaint the drawing area
    def repaint(self):
        self.queue_draw()

    ## Convert coord to screen
    def coord_to_screen(self, x, y, zl, getGlobal=False):
        mct = mapUtils.coord_to_tile((x, y, zl))
        xy = mapUtils.tile_coord_to_screen(
            (mct[0][0], mct[0][1], zl), self.get_allocation(), self.center, getGlobal
        )
        if xy:
            # return (xy[0] + mct[1][0], xy[1] + mct[1][1])
            for x, y in xy:
                return (x + mct[1][0], y + mct[1][1])

    ## Set the Graphics Context used in the visual download
    def set_visualdl_gc(self):
        if not self.visualdl_gc:
            fg_col = gtk.gdk.color_parse("#0F0")
            bg_col = gtk.gdk.color_parse("#0BB")
            self.visualdl_gc = self.window.new_gc(
                    fg_col, bg_col, None, gtk.gdk.COPY,
                    gtk.gdk.SOLID, None, None, None,
                    gtk.gdk.INCLUDE_INFERIORS,
                    0, 0, 0, 0, True, 3, gtk.gdk.LINE_DOUBLE_DASH,
                    gtk.gdk.CAP_NOT_LAST, gtk.gdk.JOIN_ROUND)
            self.visualdl_gc.set_dashes(0, [3])
            self.visualdl_gc.set_rgb_fg_color(fg_col)
            self.visualdl_gc.set_rgb_bg_color(bg_col)
            self.visualdl_lo = pango.Layout(self.get_pango_context())
            self.visualdl_lo.set_font_description(
                pango.FontDescription("sans normal 12"))

    ## Set the Graphics Context used in the scale
    def set_scale_gc(self):
        if not self.scale_gc:
            fg_scale = gtk.gdk.color_parse("#000")
            bg_scale = gtk.gdk.color_parse("#FFF")
            self.scale_gc = self.window.new_gc(
                    fg_scale, bg_scale, None, gtk.gdk.INVERT,
                    gtk.gdk.SOLID, None, None, None,
                    gtk.gdk.INCLUDE_INFERIORS,
                    0, 0, 0, 0, True, 3, gtk.gdk.LINE_SOLID,
                    gtk.gdk.CAP_NOT_LAST, gtk.gdk.JOIN_MITER)
            self.scale_gc.set_rgb_bg_color(bg_scale)
            self.scale_gc.set_rgb_fg_color(fg_scale)
            self.scale_lo = pango.Layout(self.get_pango_context())
            self.scale_lo.set_font_description(
                pango.FontDescription("sans normal 10"))

    def set_track_gc(self, initial_color):
        if not self.track_gc:
            color = gtk.gdk.color_parse(initial_color)
            self.track_gc = self.window.new_gc(
                color, color, None, gtk.gdk.COPY,
                gtk.gdk.SOLID, None, None, None,
                gtk.gdk.CLIP_BY_CHILDREN, 0, 0, 0,
                0, False, 1, gtk.gdk.LINE_SOLID,
                gtk.gdk.CAP_ROUND, gtk.gdk.JOIN_BEVEL)

    def set_gps_track_gc(self, initial_color):
        if not self.gps_track_gc:
            color = gtk.gdk.color_parse(initial_color)
            self.gps_track_gc = self.window.new_gc(
                color, color, None, gtk.gdk.COPY,
                gtk.gdk.SOLID, None, None, None,
                gtk.gdk.CLIP_BY_CHILDREN, 0, 0, 0,
                0, False, 1, gtk.gdk.LINE_SOLID,
                gtk.gdk.CAP_ROUND, gtk.gdk.JOIN_BEVEL)

    ## Set the graphics context for the gps arrow
    def set_arrow_gc(self):
        if not self.arrow_gc:
            fg_arrow = gtk.gdk.color_parse("#777")
            bg_arrow = gtk.gdk.color_parse("#FFF")
            self.arrow_gc = self.window.new_gc(
                    fg_arrow, bg_arrow, None, gtk.gdk.INVERT,
                    gtk.gdk.SOLID, None, None, None,
                    gtk.gdk.INCLUDE_INFERIORS,
                    0, 0, 0, 0, True, 2, gtk.gdk.LINE_SOLID,
                    gtk.gdk.CAP_NOT_LAST, gtk.gdk.JOIN_MITER)
            self.arrow_gc.set_rgb_bg_color(bg_arrow)
            self.arrow_gc.set_rgb_fg_color(fg_arrow)

    ## Draws a circle
    def draw_circle(self, screen_coord, gc):
        radius = 10
        self.window.draw_arc(
            gc, True, screen_coord[0] - radius, screen_coord[1] - radius,
            radius * 2, radius * 2, 0, 360 * 64
        )

    ## Draws a point
    def draw_point(self, screen_coord, gc):
        self.window.draw_point(
            gc, screen_coord[0], screen_coord[1]
        )

    ## Draws a circle as starting point for ruler
    def draw_stpt(self, mcoord, zl):
        radius = 5
        gc = self.scale_gc
        screen_coord = self.coord_to_screen(mcoord[0], mcoord[1], zl)
        self.window.draw_arc(
            gc, True, screen_coord[0] - radius, screen_coord[1] - radius,
            radius * 2, radius * 2, 0, 360 * 64
        )

    ## Draws an image
    def draw_image(self, screen_coord, img, width, height):
        self.window.draw_pixbuf(
            self.style.black_gc, img, 0, 0,
            screen_coord[0] - width / 2, screen_coord[1] - height / 2,
            width, height
        )

    def w_draw_line(self, gc, x1, y1, x2, y2):
        self.window.draw_line(gc, int(x1), int(y1), int(x2), int(y2))

    def draw_arrow(self, screen_coord, direction):
        arrow_length = 50
        self.set_arrow_gc()
        rad = math.radians(direction)
        sin = math.sin(rad)
        cos = math.cos(rad)

        arrowtop = (screen_coord[0] + arrow_length * sin, screen_coord[1] - arrow_length * cos)

        self.w_draw_line(self.arrow_gc,
                screen_coord[0],
                screen_coord[1],
                arrowtop[0],
                arrowtop[1])
        # TODO: Arrow pointers
        # self.w_draw_line(self.arrow_gc,
        #         arrowtop[0], arrowtop[1],
        #         arrowtop[0] + 7 * math.cos(direction + 3 * math.pi / 4.0),
        #         arrowtop[1] + 7 * math.sin(direction + 3 * math.pi / 4.0))
        # self.w_draw_line(self.arrow_gc,
        #         arrowtop[0], arrowtop[1],
        #         arrowtop[0] + 7 * math.cos(direction - 3 * math.pi / 4.0),
        #         arrowtop[1] + 7 * math.sin(direction - 3 * math.pi / 4.0))

    ## Draws the marker
    def draw_marker(self, conf, mcoord, zl, img, pixDim, marker_name):
        screen_coord = self.coord_to_screen(mcoord[0], mcoord[1], zl)
        if screen_coord:
            gc = self.scale_gc
            cPos = marker_name.find('#')
            if (cPos > -1):
                try:
                    my_gc = self.window.new_gc()
                    color = gtk.gdk.color_parse(marker_name[cPos:cPos + 7])
                    my_gc.set_rgb_fg_color(color)
                    gc = my_gc
                except:
                    pass
            if marker_name.startswith('point'):
                self.draw_point(screen_coord, gc)
            elif marker_name.startswith('circle'):
                self.draw_circle(screen_coord, gc)
            else:
                self.draw_image(screen_coord, img, pixDim, pixDim)
                if conf.show_marker_name:
                    # Display the Marker Name
                    gco = self.window.new_gc()
                    gco.set_rgb_fg_color(gtk.gdk.color_parse(conf.marker_font_color))

                    pangolayout = self.create_pango_layout(marker_name)
                    pangolayout.set_font_description(
                            pango.FontDescription(conf.marker_font_desc))
                    self.wr_pltxt(gco, screen_coord[0], screen_coord[1], pangolayout)

    ## Show the text
    def wr_pltxt(self, gc, x, y, pl):
        gc1 = self.window.new_gc()
        gc1.line_width = 2
        gc1.set_rgb_fg_color(gtk.gdk.color_parse("#000000"))
        self.window.draw_layout(gc1, x - 1, y - 1, pl)
        self.window.draw_layout(gc1, x, y - 1, pl)
        self.window.draw_layout(gc1, x + 1, y - 1, pl)
        self.window.draw_layout(gc1, x + 1, y, pl)
        self.window.draw_layout(gc1, x + 1, y + 1, pl)
        self.window.draw_layout(gc1, x, y + 1, pl)
        self.window.draw_layout(gc1, x - 1, y + 1, pl)
        self.window.draw_layout(gc1, x - 1, y, pl)
        self.window.draw_layout(gc, x, y, pl)

    ## Draw the second layer of elements
    def draw_overlay(self, zl, conf, crossPixbuf, dlpixbuf,
                    downloading=False, visual_dlconfig={},
                    marker=None, locations={}, entry_name="",
                    showMarkers=False, gps=None, gps_track=None,
                    r_coord=[],
                    tracks=None, draw_track_distance=False,
                    cur_coord=None):
        self.set_scale_gc()
        self.set_visualdl_gc()
        rect = self.get_allocation()
        middle = (rect.width / 2, rect.height / 2)
        full = (rect.width, rect.height)

        if (self.markerThread is not None):
            self.markerThread.cancel()

        if tracks:
            self.draw_tracks(conf.units, tracks, zl, conf.gps_track_width, draw_track_distance)

        if conf.gps_track and len(gps_track.points) > 1:
            self.draw_gps_line(conf.units, gps_track, zl, conf.gps_track_width)

        # Draw the Ruler lines
        if len(r_coord) >= 1:
            self.draw_ruler_lines(conf.units, r_coord, zl, conf.gps_track_width)

        if showMarkers:
            pixDim = marker.get_pixDim(zl)
            # Draw the selected location
            if (entry_name in locations.keys()):
                coord = locations.get(unicode(entry_name))
                screen_coord = self.coord_to_screen(coord[0], coord[1], zl)
                if screen_coord:
                    img = marker.get_marker_pixbuf(zl, 'marker1.png')
                    self.draw_image(screen_coord, img, pixDim, pixDim)
            else:
                coord = (None, None, None)

            # Draw the markers
            self.markerThread = Timer(conf.overlay_delay, self.draw_markers_thread, [zl, marker, coord, conf, pixDim])
            self.markerThread.start()

        # Draw the downloading notification
        if downloading:
            self.window.draw_pixbuf(
                self.style.black_gc, dlpixbuf, 0, 0, 0, 0, -1, -1)

        if visual_dlconfig != {}:
            self.draw_visual_dlconfig(visual_dlconfig, middle, full, zl)

        # Draw scale
        if conf.scale_visible:
            self.draw_scale(full, zl, cur_coord[0], conf)

        # Draw cross in the center
        if conf.show_cross:
            self.draw_image(middle, crossPixbuf, 12, 12)

        # Draw GPS position
        if gps and gps.gpsfix:
            location = gps.get_location()
            if location is not None and zl <= conf.max_gps_zoom:
                img = gps.pixbuf
                screen_coord = self.coord_to_screen(location[0], location[1], zl)
                if screen_coord:
                    self.draw_image(screen_coord, img,
                        GPS_IMG_SIZE[0], GPS_IMG_SIZE[1])
                    if gps.gpsfix.speed >= 0.5:  # draw arrow only, if speed is over 0.5 knots
                        self.draw_arrow(screen_coord, gps.gpsfix.track)
            if gps.mode != GPS_DISABLED and gps.gpsfix.mode == MODE_NO_FIX:
                gc = self.style.black_gc
                gc.set_rgb_fg_color(gtk.gdk.color_parse('#FF0000'))
                self.write_text(gc, middle[0] - 160, 0, 'INVALID GPS DATA', 28)

    def draw_markers(self, zl, marker, coord, conf, pixDim):
        img = marker.get_marker_pixbuf(zl)
        for string in marker.positions.keys():
            mpos = marker.positions[string]
            if (zl <= mpos[2]) and (mpos[0], mpos[1]) != (coord[0], coord[1]):
                self.draw_marker(conf, mpos, zl, img, pixDim, string)

    def draw_markers_thread(self, *args):
        try:
            self.draw_markers(args[0], args[1], args[2], args[3], args[4])
        except:
            pass

    def draw_scale(self, full, zl, latitude, conf):
        scaledata = mapUtils.friendly_scale(zl, latitude, conf.units)
        if scaledata[1] < 1:
            scalestr = "%.2f %s" % (scaledata[1], DISTANCE_UNITS[conf.units])
        elif scaledata[1] < 10:
            scalestr = "%.1f %s" % (scaledata[1], DISTANCE_UNITS[conf.units])
        else:
            scalestr = "%.0f %s" % (scaledata[1], DISTANCE_UNITS[conf.units])
        self.scale_lo.set_text(scalestr)
        self.window.draw_line(self.scale_gc, 10, full[1] - 10, 10, full[1] - 15)
        self.window.draw_line(self.scale_gc, 10, full[1] - 10, scaledata[0] + 10, full[1] - 10)
        self.window.draw_line(self.scale_gc, scaledata[0] + 10, full[1] - 10, scaledata[0] + 10, full[1] - 15)
        self.window.draw_layout(self.scale_gc, 15, full[1] - 25, self.scale_lo)

    def draw_visual_dlconfig(self, visual_dlconfig, middle, full, zl):
        sz = visual_dlconfig.get("sz", 4)
        # Draw a rectangle
        if visual_dlconfig.get("show_rectangle", False):
            width = visual_dlconfig.get("width_rect", 0)
            height = visual_dlconfig.get("height_rect", 0)
            if width > 0 and height > 0:
                self.window.draw_rectangle(
                    self.scale_gc, True,
                    visual_dlconfig.get("x_rect", 0),
                    visual_dlconfig.get("y_rect", 0),
                    width, height
                )
        # Draw the download utility
        elif visual_dlconfig.get("active", False):
            thezl = str(zl + visual_dlconfig.get("zl", -2))
            self.visualdl_lo.set_text(thezl)
            self.window.draw_rectangle(self.visualdl_gc, False,
                    middle[0] - full[0] / (sz * 2),
                    middle[1] - full[1] / (sz * 2), full[0] / sz, full[1] / sz)
            self.window.draw_layout(self.visualdl_gc,
                    middle[0] + full[0] / (sz * 2) - len(thezl) * 10,
                    middle[1] - full[1] / (sz * 2),
                    self.visualdl_lo)

        if visual_dlconfig.get('qd', 0) > 0:
            self.visualdl_lo.set_text(
                    str(visual_dlconfig.get('recd', 0)) + "/" +
                    str(visual_dlconfig.get('qd', 0)))
            if sz == 1:
                ypos = -15
            else:
                ypos = 0
            self.window.draw_layout(self.visualdl_gc,
                    middle[0],
                    middle[1] + full[1] / (sz * 2) + ypos,
                    self.visualdl_lo)

    ## Draw line with zoomlevel, [points], color, width and optional distance string
    # returns used gc (to be used in write_text for example)
    def draw_line(self, unit, zl, points, color, width, draw_distance=False):
        gc = self.style.black_gc
        gc.line_width = width
        gc.set_rgb_fg_color(gtk.gdk.color_parse(color))
        dist_str = None
        total_distance = 0

        def do_draw(ini, end):
            self.window.draw_line(gc, ini[0], ini[1], end[0], end[1])
            if dist_str:
                self.write_text(gc, end[0], end[1], dist_str, 10)

        for j in range(len(points) - 1):
            if draw_distance:
                distance = mapUtils.countDistanceFromLatLon(points[j].getLatLon(), points[j + 1].getLatLon())
                if unit != UNIT_TYPE_KM:
                    distance = mapUtils.convertUnits(UNIT_TYPE_KM, unit, distance)
                total_distance += distance
                dist_str = '%.3f %s \n%.3f %s' % (distance, DISTANCE_UNITS[unit], total_distance, DISTANCE_UNITS[unit])
            ini = self.coord_to_screen(points[j].latitude, points[j].longitude, zl)
            end = self.coord_to_screen(points[j + 1].latitude, points[j + 1].longitude, zl)
            if ini and end:
                do_draw(ini, end)
            elif ini or end:
                if ini:
                    end = self.coord_to_screen(points[j + 1].latitude, points[j + 1].longitude, zl, True)
                if end:
                    ini = self.coord_to_screen(points[j].latitude, points[j].longitude, zl, True)
                do_draw(ini, end)
        return gc

    ## Write text to point in screen coord -format
    def write_text(self, gc, x, y, text, fontsize=12):
        pangolayout = self.create_pango_layout("")
        pangolayout.set_font_description(pango.FontDescription("sans normal %s" % fontsize))
        pangolayout.set_text(text)
        self.wr_pltxt(gc, x, y, pangolayout)

    ## Write text to point in (lat, lon) -format
    def write_text_lat_lon(self, gc, zl, point, text):
        screen_coord = self.coord_to_screen(point.latitude, point.longitude, zl)
        if screen_coord:
            self.write_text(gc, screen_coord[0], screen_coord[1], text)

    def draw_ruler_lines(self, unit, points, zl, track_width):
        color = 'green'
        self.draw_line(unit, zl, points, color, track_width, True)

    def draw_gps_line(self, unit, track, zl, track_width):
        if not self.gpsTrackInst:
            self.set_gps_track_gc('red')
            colors = ['red']
            self.gpsTrackInst = self.TrackThread(self, self.gps_track_gc,
                colors, unit, [copy.deepcopy(track)], zl, track_width, False, False)
            self.gpsTrackInst.start()
        else:
            update_all = False
            if len(self.gpsTrackInst.tracks[0].points) != len(track.points):
                update_all = True
                self.gpsTrackInst.tracks = [copy.deepcopy(track)]
            if self.gpsTrackInst.zl != zl:
                update_all = True
            self.gpsTrackInst.unit = unit
            self.gpsTrackInst.zl = zl
            self.gpsTrackInst.track_width = track_width
            if update_all:
                self.gpsTrackInst.update_all.set()
            self.gpsTrackInst.update.set()  # call update on TrackThread

    def draw_tracks(self, unit, tracks, zl, track_width, draw_distance=False):
        if not self.trackThreadInst:
            self.set_track_gc('blue')
            colors = ['purple', 'blue', 'yellow', 'pink', 'brown', 'orange', 'black']
            self.trackThreadInst = self.TrackThread(self, self.track_gc,
                colors, unit, copy.copy(tracks), zl, track_width, True, draw_distance)
            self.trackThreadInst.start()
        else:
            update_all = False
            if self.trackThreadInst.zl != zl or self.trackThreadInst.tracks != tracks:
                update_all = True
            self.trackThreadInst.unit = unit
            self.trackThreadInst.tracks = copy.copy(tracks)
            self.trackThreadInst.zl = zl
            self.trackThreadInst.track_width = track_width
            self.trackThreadInst.draw_distance = draw_distance
            if update_all:
                self.trackThreadInst.update_all.set()
                self.trackThreadInst.update.set()
            else:
                if self.trackTimer:
                    self.trackTimer.cancel()
                self.trackTimer = Timer(conf.overlay_delay, self.trackThreadInst.update.set)
                self.trackTimer.start()

    class TrackThread(Thread):
        def __init__(self, da, gc, colors, unit, tracks, zl, track_width, draw_start_end=True, draw_distance=False):
            Thread.__init__(self)
            self.da = da
            self.gc = gc
            self.colors = colors
            self.unit = unit
            self.tracks = tracks
            self.zl = zl
            self.track_width = track_width
            self.draw_start_end = draw_start_end
            self.draw_distance = draw_distance
            self.screen_coords = {}
            self.update = Event()
            self.update.set()
            self.update_all = Event()
            self.update_all.set()
            self.__stop = Event()

            self.setDaemon(True)

        def run(self):
            while not self.__stop.is_set():
                self.update.wait()      # Wait for update signal to start updating
                self.update.clear()     # Clear the signal straight away to allow stopping of the update
                if self.update_all.is_set():
                    print 'update_all'
                    self.update_all.clear()
                    rect = self.da.get_allocation()
                    self.base_point = mapUtils.pointer_to_coord(rect, (0, 0), self.da.center, self.zl)
                    for track in self.tracks:
                        self.screen_coords[track] = []
                        for i in range(len(track.points)):
                            if self.update_all.is_set() or self.__stop.is_set():
                                break
                            self.screen_coords[track].append(
                                self.da.coord_to_screen(track.points[i].latitude, track.points[i].longitude, self.zl, True)
                                )
                i = 0
                for track in self.tracks:
                    track_color = self.colors[i % len(self.colors)]
                    self.draw_line(track, track_color)
                    i += 1

        def stop(self):
            self.__stop.set()

        def draw_line(self, track, track_color):
            self.gc.line_width = self.track_width
            self.gc.set_rgb_fg_color(gtk.gdk.color_parse(track_color))

            def do_draw(ini, end, dist_str=None):
                gtk.threads_enter()
                try:
                    self.da.window.draw_line(self.gc, ini[0], ini[1], end[0], end[1])
                    if dist_str:
                        self.da.write_text(self.gc, end[0], end[1], dist_str, 10)
                finally:
                    gtk.threads_leave()

            cur_coord = self.da.coord_to_screen(self.base_point[0], self.base_point[1], self.zl, True)

            rect = self.da.get_allocation()
            center = (rect.width / 2, rect.height / 2)
            threshold = 1000  # in pixels
            threshold_x = threshold + center[0]
            threshold_y = threshold + center[1]
            mod_x = cur_coord[0] - center[0]
            mod_y = cur_coord[1] - center[1]

            start = time.time()
            dist_str = None
            for j in range(len(self.screen_coords[track]) - 1):
                # If update or __stop was set while we're in the loop, break
                if self.update.is_set() or self.__stop.is_set():
                    return
                if abs(self.screen_coords[track][j][0] + mod_x) < threshold_x \
                  and abs(self.screen_coords[track][j][1] + mod_y) < threshold_y:
                    if self.draw_distance:
                        distance = mapUtils.countDistanceFromLatLon(track.points[j].getLatLon(), track.points[j + 1].getLatLon())
                        if self.unit != UNIT_TYPE_KM:
                            distance = mapUtils.convertUnits(UNIT_TYPE_KM, self.unit, distance)
                        dist_str = '%.3f %s' % (distance, DISTANCE_UNITS[self.unit])
                    ini = (self.screen_coords[track][j][0] + cur_coord[0], self.screen_coords[track][j][1] + cur_coord[1])
                    end = (self.screen_coords[track][j + 1][0] + cur_coord[0], self.screen_coords[track][j + 1][1] + cur_coord[1])
                    if ini and end:
                        do_draw(ini, end, dist_str)
            print 'drawing: %.3fs' % (time.time() - start)

            if self.draw_start_end:
                if track.distance:
                    distance = mapUtils.convertUnits(UNIT_TYPE_KM, self.unit, track.distance)
                    text = '%s - %.2f %s' % (track.name, distance, DISTANCE_UNITS[self.unit])
                else:
                    text = track.name
                gtk.threads_enter()     # Precautions to tell GTK that we're drawing from a thread now
                try:
                    self.da.write_text(self.gc, self.screen_coords[track][0][0] + cur_coord[0],
                        self.screen_coords[track][0][1] + cur_coord[1], '%s (start)' % text)
                    self.da.write_text(self.gc, self.screen_coords[track][-1][0] + cur_coord[0],
                        self.screen_coords[track][-1][1] + cur_coord[1], '%s (end)' % text)
                finally:
                    gtk.threads_leave()  # And once we are finished, tell that as well...
