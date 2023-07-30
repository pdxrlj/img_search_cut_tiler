import os
import shutil
import sys
import tempfile
from uuid import uuid4
from xml.etree import ElementTree

from osgeo import gdal, osr

from mercator import MercatorTool


class TileDetail:
    tx = 0
    ty = 0
    tz = 0
    rx = 0
    ry = 0
    rxsize = 0
    rysize = 0
    wx = 0
    wy = 0
    wxsize = 0
    wysize = 0

    def __init__(self, **kwargs):
        for key in kwargs:
            if hasattr(self, key):
                setattr(self, key, kwargs[key])


class TileJobInfo(object):
    srcFile = ""
    nbDataBands = 0
    outputFilePath = ""
    tminmax = []
    tminz = 0
    tmaxz = 0
    outGeoTrans = []

    def __init__(self, **kwargs):
        for key in kwargs:
            if hasattr(self, key):
                setattr(self, key, kwargs[key])


class tile_job:
    def __init__(self, input_file, output_folder, options):
        self.tminmax = None
        self.ominy = None
        self.omaxx = None
        self.omaxy = None
        self.ominx = None
        self.data_band_count = 4
        self.input_file = input_file
        self.output_folder = output_folder

        self.vrt_filename = os.path.join(tempfile.mkdtemp(), str(uuid4()) + ".vrt")

        self.options = options
        minmax = self.options.zoom.split("-", 1)
        zoom_min, zoom_max = minmax[:2]
        self.zoom_min = int(zoom_min)
        if zoom_max:
            self.zoom_max = int(zoom_max)
        else:
            self.zoom_max = self.zoom_min

        self.warped_dataset = None
        self.mercator = MercatorTool()

    def update_no_data_value(self):
        def gdal_vrt_warp(options, key, value):
            tb = ElementTree.TreeBuilder()
            tb.start("Option", {"name": key})
            tb.data(value)
            tb.end("Option")
            element = tb.close()
            options.insert(0, element)

        temp_file = tempfile.mktemp("-tile_job.vrt")
        # temp_file = "-tile_job.vrt"
        self.warped_dataset.GetDriver().CreateCopy(temp_file, self.warped_dataset)
        with open(temp_file, 'r', encoding="utf-8") as f:
            vrt_string = f.read()
            vrt_root = ElementTree.fromstring(vrt_string)
            options = vrt_root.find("GDALWarpOptions")
            gdal_vrt_warp(options, "INIT_DEST", "NO_DATA")
            gdal_vrt_warp(options, "UNIFIED_SRC_NODATA", "YES")
            vrt_string = ElementTree.tostring(vrt_root, encoding="utf-8").decode("utf-8")

        with open(temp_file, 'w', encoding="utf-8") as f:
            f.write(vrt_string)
        corrected_dataset = gdal.Open(temp_file)
        # 删除文件
        os.remove(temp_file)
        corrected_dataset.SetMetadataItem("NODATA_VALUES", "0 0 0 0")
        self.warped_dataset = corrected_dataset

    def open_data(self):
        gdal.AllRegister()
        print(f"input_file:{self.input_file}")
        input_dataset = gdal.Open(self.input_file, gdal.GA_ReadOnly)
        if input_dataset is None:
            raise Exception("无法打开文件")

        geo_transform = input_dataset.GetGeoTransform()
        if geo_transform is None:
            raise Exception("无法获取地理坐标")

        gcp_count = input_dataset.GetGCPCount()
        if gcp_count != 0:
            raise Exception("无法处理GCP")

        input_srs = osr.SpatialReference()
        input_srs.ImportFromWkt(input_dataset.GetProjectionRef())
        dst_srs = osr.SpatialReference()
        dst_srs.ImportFromEPSG(3857)
        self.warped_dataset = gdal.AutoCreateWarpedVRT(input_dataset, input_srs.ExportToWkt(), dst_srs.ExportToWkt())

        # 设置波段的无效值
        self.update_no_data_value()
        self.warped_dataset.GetDriver().CreateCopy(self.vrt_filename, self.warped_dataset)

        warped_geo_transform = self.warped_dataset.GetGeoTransform()

        self.ominx = warped_geo_transform[0]
        self.omaxy = warped_geo_transform[3]
        self.omaxx = self.ominx + warped_geo_transform[1] * self.warped_dataset.RasterXSize
        self.ominy = self.omaxy - warped_geo_transform[1] * self.warped_dataset.RasterYSize

        self.tminmax = list(range(0, 32))
        for tz in range(0, 32):
            tminx, tminy = self.mercator.meters_to_tile(self.ominx, self.ominy, tz)
            tmaxx, tmaxy = self.mercator.meters_to_tile(self.omaxx, self.omaxy, tz)
            tminx, tminy = max(0, tminx), max(0, tminy)
            tmaxx, tmaxy = min(2 ** tz - 1, tmaxx), min(2 ** tz - 1, tmaxy)

            self.tminmax[tz] = (tminx, tminy, tmaxx, tmaxy)

    def geo_query(self, ulx, uly, lrx, lry):
        ds = self.warped_dataset
        geotran = ds.GetGeoTransform()
        rx = int((ulx - geotran[0]) / geotran[1] + 0.001)
        ry = int((uly - geotran[3]) / geotran[5] + 0.001)
        rxsize = int((lrx - ulx) / geotran[1] + 0.5)
        rysize = int((lry - uly) / geotran[5] + 0.5)
        wxsize, wysize = 4 * 256, 4 * 256
        wx = 0
        if rx < 0:
            rxshift = abs(rx)
            wx = int(wxsize * (float(rxshift) / rxsize))
            wxsize = wxsize - wx
            rxsize = rxsize - int(rxsize * (float(rxshift) / rxsize))
            rx = 0
        if rx + rxsize > ds.RasterXSize:
            wxsize = int(wxsize * (float(ds.RasterXSize - rx) / rxsize))
            rxsize = ds.RasterXSize - rx
        wy = 0
        if ry < 0:
            ryshift = abs(ry)
            wy = int(wysize * (float(ryshift) / rysize))
            wysize = wysize - wy
            rysize = rysize - int(rysize * (float(ryshift) / rysize))
            ry = 0
        if ry + rysize > ds.RasterYSize:
            wysize = int(wysize * (float(ds.RasterYSize - ry) / rysize))
            rysize = ds.RasterYSize - ry
        return (rx, ry, rxsize, rysize), (wx, wy, wxsize, wysize)

    def make_base_tiles(self):
        tminx, tminy, tmaxx, tmaxy = self.tminmax[self.zoom_max]
        tile_details = []
        tz = self.zoom_max
        for ty in range(tmaxy, tminy - 1, -1):
            for tx in range(tminx, tmaxx + 1):
                tile_filename = os.path.join(self.output_folder, str(tz), str(tx), "%s.png" % ty)
                if os.path.exists(os.path.dirname(tile_filename)) is False:
                    os.makedirs(os.path.dirname(tile_filename))
                b = self.mercator.tile_bounds(tx, ty, tz)
                rb, wb = self.geo_query(b[0], b[3], b[2], b[1])
                rx, ry, rxsize, rysize = rb
                wx, wy, wxsize, wysize = wb
                tile_details.append(
                    TileDetail(
                        tx=tx,
                        ty=ty,
                        tz=tz,
                        rx=rx,
                        ry=ry,
                        rxsize=rxsize,
                        rysize=rysize,
                        wx=wx,
                        wy=wy,
                        wxsize=wxsize,
                        wysize=wysize
                    )
                )
        conf = TileJobInfo(
            srcFile=self.vrt_filename,
            nbDataBands=self.data_band_count,
            outputFilePath=self.output_folder,
            tminmax=self.tminmax,
            tminz=self.zoom_min,
            tmaxz=self.zoom_max,
        )
        return conf, tile_details


class SingleProcessTiling:
    def __init__(self, input_file, output_folder, options):
        self.total = 0
        self.tile_job_info = TileJobInfo()
        self.input_file = input_file
        self.output_folder = output_folder
        self.options = options
        self.progress_bar()

        # overview tile
        self.create_overview_tiles()
        print(f"删除生成的vrt文件：{self.tile_job_info.srcFile}")
        shutil.rmtree(os.path.dirname(self.tile_job_info.srcFile))

    def progress_bar(self):
        tile_details = self.worker_tile_details()
        tile_count = len(tile_details)
        self.total += tile_count
        pb = progress_bar(tile_count, "切割顶层瓦片")
        pb.start()
        for tile_detail in tile_details:
            self.create_base_tile(tile_detail)
            pb.update_progress()

    def create_base_tile(self, tile_detail):
        gdal.AllRegister()
        tile_job_info = self.tile_job_info
        output = tile_job_info.outputFilePath
        tile_bands = tile_job_info.nbDataBands
        ds = gdal.Open(tile_job_info.srcFile, gdal.GA_ReadOnly)
        mem_drv = gdal.GetDriverByName('MEM')
        out_drv = gdal.GetDriverByName("PNG")
        alpha_band = ds.GetRasterBand(1).GetMaskBand()

        tx = tile_detail.tx
        ty = tile_detail.ty
        tz = tile_detail.tz
        rx = tile_detail.rx
        ry = tile_detail.ry
        rxsize = tile_detail.rxsize
        rysize = tile_detail.rysize
        wx = tile_detail.wx
        wy = tile_detail.wy
        wxsize = tile_detail.wxsize
        wysize = tile_detail.wysize
        query_size = 4 * 256
        tile_filename = os.path.join(output, str(tz), str(tx), f"{ty}.png")
        dstile = mem_drv.Create('', 256, 256, tile_bands)
        data = alpha = None
        if rxsize != 0 and rysize != 0 and wxsize != 0 and wysize != 0:
            data = ds.ReadRaster(rx, ry, rxsize, rysize, wxsize, wysize, band_list=list(range(1, tile_bands)))
            alpha = alpha_band.ReadRaster(rx, ry, rxsize, rysize, wxsize, wysize)
            if data:
                dsquery = mem_drv.Create('', query_size, query_size, tile_bands)
                dsquery.WriteRaster(wx, wy, wxsize, wysize, data, band_list=list(range(1, tile_bands)))
                dsquery.WriteRaster(wx, wy, wxsize, wysize, alpha, band_list=[tile_bands])
                self.scale_query_to_tile(dsquery, dstile, tile_filename)
                del dsquery
        del ds
        del data
        out_drv.CreateCopy(tile_filename, dstile, strict=0)
        del dstile

    def create_overview_tiles(self):
        tile_job_info = self.tile_job_info
        mem_driver = gdal.GetDriverByName('MEM')
        out_driver = gdal.GetDriverByName("PNG")
        tile_bands = tile_job_info.nbDataBands
        tcount = 0
        for tz in range(tile_job_info.tmaxz - 1, tile_job_info.tminz - 1, -1):
            tminx, tminy, tmaxx, tmaxy = tile_job_info.tminmax[tz]
            tcount += (1 + abs(tmaxx - tminx)) * (1 + abs(tmaxy - tminy))
        if tcount == 0:
            return
        self.total += tcount
        pb = progress_bar(tcount, '切割下层瓦片')
        pb.start()
        for tz in range(tile_job_info.tmaxz - 1, tile_job_info.tminz - 1, -1):
            tminx, tminy, tmaxx, tmaxy = tile_job_info.tminmax[tz]
            for ty in range(tmaxy, tminy - 1, -1):
                for tx in range(tminx, tmaxx + 1):
                    tile_filename = os.path.join(self.output_folder, str(tz), str(tx), "%s.%s" % (ty, "png"))
                    if not os.path.exists(os.path.dirname(tile_filename)):
                        os.makedirs(os.path.dirname(tile_filename))
                    dsquery = mem_driver.Create('', 2 * 256, 2 * 256, tile_bands)
                    dstile = mem_driver.Create('', 256, 256, tile_bands)
                    for y in range(2 * ty, 2 * ty + 2):
                        for x in range(2 * tx, 2 * tx + 2):
                            minx, miny, maxx, maxy = tile_job_info.tminmax[tz + 1]

                            if minx <= x <= maxx and miny <= y <= maxy:
                                path = os.path.join(self.output_folder, str(tz + 1), str(x), "%s.%s" % (y, "png"))
                                dsquerytile = gdal.Open(path, gdal.GA_ReadOnly)
                                if (ty == 0 and y == 1) or (ty != 0 and (y % (2 * ty)) != 0):
                                    tileposy = 0
                                else:
                                    tileposy = 256
                                if tx:
                                    tileposx = x % (2 * tx) * 256
                                elif tx == 0 and x == 1:
                                    tileposx = 256
                                else:
                                    tileposx = 0
                                temp_raster = dsquerytile.ReadRaster(0, 0, 256, 256)
                                dsquery.WriteRaster(tileposx, tileposy, 256, 256, temp_raster,
                                                    band_list=list(range(1, tile_bands + 1)))
                    self.scale_query_to_tile(dsquery, dstile, tile_filename=tile_filename)
                    out_driver.CreateCopy(tile_filename, dstile, strict=0)
                    pb.update_progress()

    def scale_query_to_tile(self, dsquery, dstile, tile_filename=''):
        tile_bands = dstile.RasterCount
        for i in range(1, tile_bands + 1):
            res = gdal.RegenerateOverview(dsquery.GetRasterBand(i), dstile.GetRasterBand(i), 'average')
            if res != 0:
                raise Exception("RegenerateOverview() failed on %s, error %d" % (tile_filename, res))

    def worker_tile_details(self):
        tile_job_details = tile_job(self.input_file, self.output_folder, self.options)
        tile_job_details.open_data()
        conf, tile_details = tile_job_details.make_base_tiles()
        self.tile_job_info = conf
        return tile_details


class progress_bar:
    def __init__(self, total_items, title):
        sys.stdout.write("%s 共%d张 \n" % (title, total_items))
        self.total_items = total_items
        self.nb_items_done = 0
        self.current_progress = 0
        self.STEP = 2.5

    def start(self):
        sys.stdout.write("0")

    def update_progress(self, nb_items=1):
        self.nb_items_done += nb_items
        progress = float(self.nb_items_done) / self.total_items * 100
        if progress >= self.current_progress + self.STEP:
            done = False
            while not done:
                if self.current_progress + self.STEP <= progress:
                    self.current_progress += self.STEP
                    if self.current_progress % 10 == 0:
                        sys.stdout.write(str(int(self.current_progress)))
                        if self.current_progress == 100:
                            sys.stdout.write("\n")
                    else:
                        sys.stdout.write(".")
                else:
                    done = True
        sys.stdout.flush()
