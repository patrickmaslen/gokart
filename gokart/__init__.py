import bottle
import dotenv
import os
import pytz
import shutil
import subprocess
import tempfile
import uwsgi
import requests
from datetime import datetime,timedelta
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText

dotenv.load_dotenv(dotenv.find_dotenv())

bottle.TEMPLATE_PATH.append('./gokart')
bottle.debug(True)

BASE_PATH = os.path.dirname(__file__)


ENV_TYPE = (os.environ.get("ENV_TYPE") or "prod").lower()
# serve up map apps
@bottle.route('/<app>')
def index(app):
    return bottle.template('index.html', app=app,envType=ENV_TYPE)

# WMS shim for Himawari 8
# Landgate tile servers, round robin
FIREWATCH_TZ = pytz.timezone('Australia/Perth')
FIREWATCH_SERVICE = "/mapproxy/firewatch/service"
FIREWATCH_GETCAPS = FIREWATCH_SERVICE + "?service=wms&request=getcapabilities"
HTTPS_VERIFY = os.environ.get("HTTPS_VERIFY") or "True"
HTTPS_VERIFY = True if HTTPS_VERIFY.lower() in ["true","on","yes"] else (False if HTTPS_VERIFY.lower() in ["false","off","no"] else HTTPS_VERIFY )


@bottle.route("/hi8/<target>")
def himawari8(target):
    baseUrl = bottle.request.url[0:bottle.request.url.find("/hi8")]
    if uwsgi.cache_exists("himawari8"):
        getcaps = uwsgi.cache_get("himawari8")
    else:
        getcaps = requests.get("{}{}".format(baseUrl,FIREWATCH_GETCAPS),verify=HTTPS_VERIFY).content
        uwsgi.cache_set("himawari8", getcaps, 60*10)  # cache for 10 mins
    getcaps = getcaps.decode("utf-8")
    layernames = re.findall("\w+HI8\w+{}\.\w+".format(target), getcaps)
    layers = []
    for layer in layernames:
        layers.append([FIREWATCH_TZ.localize(datetime.strptime(re.findall("\w+_(\d+)_\w+", layer)[0], "%Y%m%d%H%M")).isoformat(), layer])
    result = {
        "servers": [baseUrl + FIREWATCH_SERVICE],
        "layers": layers
    }
    return result


# PDF renderer, accepts a JPG
@bottle.route("/gdal/<fmt>", method="POST")
def gdal(fmt):
    # needs gdal 1.10+
    extent = bottle.request.forms.get("extent").split(" ")
    jpg = bottle.request.files.get("jpg")
    workdir = tempfile.mkdtemp()
    path = os.path.join(workdir, jpg.filename)
    jpg.save(workdir)
    extra = []
    if fmt == "tif":
        of = "GTiff"
        ct = "image/tiff"
        extra = ["-co", "COMPRESS=JPEG", "-co", "PHOTOMETRIC=YCBCR", "-co", "JPEG_QUALITY=95"]
    elif fmt == "pdf":
        of = "PDF"
        ct = "application/pdf"
    subprocess.check_call([
        "gdal_translate", "-of", of, "-a_ullr", extent[0], extent[3], extent[2], extent[1],
        "-a_srs", "EPSG:4326", "-co", "DPI={}".format(bottle.request.forms.get("dpi", 150)),
        "-co", "TITLE={}".format(bottle.request.forms.get("title", "Quick Print")),
        "-co", "AUTHOR={}".format(bottle.request.forms.get("author", "Anonymous")),
        "-co", "PRODUCER={}".format(subprocess.check_output(["gdalinfo", "--version"])),
        "-co", "SUBJECT={}".format(bottle.request.headers.get('Referer', "gokart")),
        "-co", "CREATION_DATE={}".format(datetime.strftime(datetime.utcnow(), "%Y%m%d%H%M%SZ'00'"))] + extra + [
        path, path + "." + fmt
    ])
    output = open(path + "." + fmt)
    shutil.rmtree(workdir)
    bottle.response.set_header("Content-Type", ct)
    bottle.response.set_header("Content-Disposition", "attachment;filename='{}'".format(jpg.filename.replace("jpg", fmt)))
    return output


# Vector translation using ogr
@bottle.route("/ogr/<fmt>", method="POST")
def ogr(fmt):
    # needs gdal 1.10+
    json = bottle.request.files.get("json")
    workdir = tempfile.mkdtemp()
    layername = os.path.splitext(json.filename)[0]
    json.save(workdir)
    jsonfile = os.path.join(workdir, json.filename)
    extra = []
    if fmt == "shp" and False:
        #Disable now
        f = "ESRI Shapefile"
        ct = "application/zip"
    elif fmt == 'sqlite':
        f = "SQLite"
        ct = "application/x-sqlite3"
        dst_datasource = os.path.splitext(jsonfile)[0] + ".sqlite"
    elif fmt == 'gpkg':
        f = "GPKG"
        ct = "application/x-sqlite3"
        dst_datasource = os.path.splitext(jsonfile)[0] + ".gpkg"
    elif fmt == 'csv':
        f = "CSV"
        ct = "text/csv"
        dst_datasource = os.path.splitext(jsonfile)[0] + ".csv"
    else:
        bottle.response.status = 400
        return "Not supported format({})".format(fmt)

    subprocess.check_call([
        "ogr2ogr","-overwrite" , "-progress","-a_srs","EPSG:4326","-nln",layername, "-f", f,dst_datasource, jsonfile]) 

    if fmt == "shp":
        shutil.make_archive(path.replace('geojson', 'zip'), 'zip', workdir, workdir)
        dst_datasource = path + ".zip"

    output = open(dst_datasource)
    shutil.rmtree(workdir)
    bottle.response.set_header("Content-Type", ct)
    bottle.response.set_header("Content-Disposition", "attachment;filename='{}'".format(os.path.basename(dst_datasource)))
    return output


# saveas
@bottle.route("/saveas", method="POST")
def saveas():
    user = bottle.request.get_header("Remote-User","anonymous")

    f = bottle.request.files.get("file")
    filename = f.raw_filename
    f.raw_filename = "_{}_{}".format(user,bottle.request.remote_addr).join(os.path.splitext(f.raw_filename))
    workdir = os.path.join(BASE_PATH,"tmp")
    if not os.path.exists(workdir):
        #create dir if required.
        os.mkdir(workdir)

    
    path = os.path.join(workdir, f.filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except:
            pass
    f.save(workdir,overwrite=True)
    bottle.response.set_header("Content-Type", "text/plain")
    return bottle.request.url.replace("/saveas","/fetch") + "/" + f.filename + "?filename=" + filename;


application = bottle.default_app()
