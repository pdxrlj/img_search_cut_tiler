import argparse
import os.path
import sys
from uuid import uuid4

from osgeo import gdal

from tile_job import SingleProcessTiling


def process_args(args):
    print(f"args:{args}")
    parser = argparse.ArgumentParser()
    parser.add_argument('-z', dest='zoom', metavar="切片级别", help="瓦片层级如13-15", required=True)
    parser.add_argument('-p', dest="process", metavar="进程数", default=1, help="进程数")
    parser.add_argument("-i", dest="input_file", metavar="输入文件", help="输入文件", required=True)
    parser.add_argument("-o", dest="output_folder", metavar="输出文件夹", help="输出文件目录")
    args = parser.parse_args(args)
    input_file = args.input_file
    if os.path.isfile(input_file) is False:
        raise Exception(f"输入文件不存在:{input_file}")

    output_folder = args.output_folder

    if not output_folder:
        img_path_dir = os.path.dirname(input_file)
        input_file_name = os.path.basename(input_file).split(".")[0]
        output_folder = os.path.join(img_path_dir, input_file_name, str(uuid4()))
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    print(f"output_folder:{output_folder}")
    return input_file, output_folder, args


def main():
    argv = gdal.GeneralCmdLineProcessor(sys.argv)
    print(f"sys argv:{sys.argv}")
    input_file, output_folder, options = process_args(argv[1:])
    SingleProcessTiling(input_file, output_folder, options)


if __name__ == '__main__':
    main()
