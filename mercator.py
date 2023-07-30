import math


class MercatorTool:
    def __init__(self):
        self.tile_size = 256
        self.origin_shift = 2 * math.pi * 6378137 / 2.0
        self.initial_resolution = 2 * math.pi * 6378137 / self.tile_size

    def resolution(self, zoom):
        """
        :param zoom: 瓦片层级
        :return: 当前瓦片层级的分辨率
        """
        return self.initial_resolution / (2 ** zoom)

    def meters_to_tile(self, mx, my, zoom):
        """
        :param mx: 当前瓦片的范围
        :param my: 当前瓦片的范围
        :param zoom: 瓦片层级
        :return: 当前瓦片的范围
        """
        px, py = self.meters_to_pixels(mx, my, zoom)
        tx, ty = self.pixels_to_tile(px, py)
        return tx, ty

    def meters_to_pixels(self, mx, my, zoom):
        """
        :param mx: 当前瓦片的范围
        :param my: 当前瓦片的范围
        :param zoom: 瓦片层级
        :return: 当前瓦片的范围
        """
        res = self.resolution(zoom)
        px = (mx + self.origin_shift) / res
        py = (my + self.origin_shift) / res
        return px, py

    def tile_bounds(self, tx, ty, zoom):
        minx, miny = self.pixels_to_meters(tx * 256, ty * 256, zoom)
        maxx, maxy = self.pixels_to_meters((tx + 1) * 256, (ty + 1) * 256, zoom)
        return minx, miny, maxx, maxy

    def pixels_to_tile(self, px, py):
        """
        :param px: 当前瓦片x轴的像素
        :param py: 当前瓦片y轴的像素
        :return: 当前瓦片的范围
        """
        tx = int(math.ceil(px / float(self.tile_size)) - 1)
        ty = int(math.ceil(py / float(self.tile_size)) - 1)
        return tx, ty

    def pixels_to_meters(self, px, py, zoom):
        res = self.resolution(zoom)
        mx = px * res - self.origin_shift
        my = py * res - self.origin_shift
        return mx, my


if __name__ == "__main__":
    mercator_tools = MercatorTool("C:/Users/ruanyu/Desktop/黄蜡湾新村.tif")
    # _min_zoom, _max_zoom = mercator_tools.min_max_zoom()
    # print(f"min_zoom: {_min_zoom}, max_zoom: {_max_zoom}")

    mercator_tools.create_base_tile(14, 16)
    # mercator_tools.compute_tminmax(18, None)
    mercator_tools.create_overview_tiles()
