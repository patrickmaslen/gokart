import sys
import struct
import time
import subprocess
import math
import traceback
import datetime
from osgeo import ogr, osr, gdal
from affine import Affine

import json
import bottle

from .settings import *
from .jinja2settings import settings as jinja2settings

def convertEpochTimeToDatetime(t):
    """
    Convert the epoch time to the datetime with perth timezone
    """
    if t:
        datetimes = t.split()
        if len(datetimes) == 1:
            return datetime.datetime.fromtimestamp(long(datetimes[0]),PERTH_TIMEZONE)
        elif (len(datetimes) == 3 and datetimes[1].lower() == "sec" and datetimes[2].upper() == 'UTC'):
            return datetime.datetime.fromtimestamp(long(datetimes[0]),PERTH_TIMEZONE)
        else:
            raise "Invalid epoch time '{}'".format(t)

def getEpochTimeFunc(name,defaultBandIndex=None):
    """
    Get the meta data whose type is epoch time
    """
    def _func(ds,bandIndex=None):
        """
        Get the data from datasource's metadata if both band and defaultBand are None; otherwise get the data from datasource's band
        """
        try:
            if bandIndex is not None:
                dt = convertEpochTimeToDatetime(ds.GetRasterBand(bandIndex).GetMetadata().get(name))
            elif defaultBandIndex is not None:
                dt = convertEpochTimeToDatetime(ds.GetRasterBand(defaultBandIndex).GetMetadata().get(name))
            else:
                dt = convertEpochTimeToDatetime(ds.GetMetadata().get(name))

            return dt
        except:
            return None
    return _func

def getMetadataFunc(name,defaultBandIndex=None):
    """
    Get the meta data 
    """
    def _func(ds,bandIndex=None):
        """
        Get the data from datasource's metadata if both band and defaultBand are None; otherwise get the data from datasource's band
        """
        try:
            if bandIndex is not None:
                dt = ds.GetRasterBand(bandIndex).GetMetadata().get(name)
            elif defaultBandIndex is not None:
                dt = ds.GetRasterBand(defaultBandIndex).GetMetadata().get(name)
            else:
                dt = ds.GetMetadata().get(name)

            return dt
        except:
            return None
    return _func

def getUnitFunc(name,defaultBandIndex=None):
    """
    Get the meta data 
    """
    unit_map = {
        "kmh":"km/h",
        "wx":None,
        "degrees_north":None,
        "DF":None,
        "FFDI":None,
        "GFDI":None

    }
    def _func(ds,bandIndex=None):
        """
        Get the data from datasource's metadata if both band and defaultBand are None; otherwise get the data from datasource's band
        """
        try:
            if bandIndex is not None:
                dt = ds.GetRasterBand(bandIndex).GetMetadata().get(name)
            elif defaultBandIndex is not None:
                dt = ds.GetRasterBand(defaultBandIndex).GetMetadata().get(name)
            else:
                dt = ds.GetMetadata().get(name)

            return unit_map[dt] if dt in unit_map else dt
        except:
            return None
    return _func

def isNightFunc(name):
    """
    check whether band's time is night or not
    """
    def _func(ds,bandIndex=None):
        try:
            dt = convertEpochTimeToDatetime(ds.GetRasterBand(bandIndex).GetMetadata().get(name))
            return dt.hour >= 18 or dt.hour < 7 
        except:
            return False
    return _func

def getBandTimeoutFunc(name):
    """
    Get band timeout by subtract the first band's start time from the second band's start time
    if the second band or the first band does not exist, return None
    """
    getStartTimeFunc = getEpochTimeFunc(name)
    def _func(ds):
        startTime2 = getStartTimeFunc(ds,2)
        startTime1 = getStartTimeFunc(ds,1)
        if startTime2 and startTime1 :
            return (startTime2 - startTime1).total_seconds()
        else:
            return None
    return _func

def isInBandFunc(datasource,band,bandTime):
    try:
        diff = (bandTime - band["start_time"]).total_seconds()
        if diff == 0:
            return True
        elif diff < 0:
            return False
        else:
            return diff < datasource["metadata"]["band_timeout"]
    except:
        return False

def getEpsgSrs(srsid):
    srs = srsid.split(":")
    if len(srs) != 2 or srs[0] != "EPSG":
        raise Exception("Srs '{}' is not a invalid epsg srs".format(srsid))
    result = osr.SpatialReference()
    result.ImportFromEPSG(int(srs[1]))
    return result

def loadDatasource(datasource):
    """
    load the data source
    """
    datasource["status"] = "loading"
    ds = None
    try:
        #initialize ds metadata
        datasource["metadata"] = datasource.get("metadata") or {}
        for key in datasource.get("metadata_f").iterkeys():
            datasource["metadata"][key] = None

        #initialize the bands
        datasource["bands"] = datasource.get("bands") or []
        for band in datasource["bands"]:
            band.clear()

        #print "Begin to load raster datasource: ".format(datasource["datasource"])
        ds = gdal.Open(datasource["datasource"])

        if datasource.get("options") and datasource["options"].get("srs"):
            datasource["srs"] = getEpsgSrs(datasource["options"]["srs"])
        else:
            datasource["srs"] = osr.SpatialReference()
            datasource["srs"].ImportFromWkt(ds.GetProjection())

        #load ds metadata
        for key,func in datasource.get("metadata_f").iteritems():
            datasource["metadata"][key] = func(ds)

        if len(datasource["bands"]) > ds.RasterCount:
            del datasource["bands"][ds.RasterCount:]

        #load band metadata
        index = 1
        while index <= ds.RasterCount:
            if index < len(datasource["bands"]):
                band = datasource["bands"][index - 1]
            else:
                band = {}
                datasource["bands"].append(band)
            band["index"] = index
            for key,func in datasource.get("band_metadata_f").iteritems():
                band[key] = func(ds,index)
            #print "Band {} = {}".format(index,bandid)
            index+=1

        if "name" not in datasource:
            datasource["name"] = datasource.get("metadata",{}).get("name","")

        datasource["status"] = "loaded"
        print "End to load raster datasource:{} metadata:{} ".format(datasource["file"],datasource["metadata"])
    except:
        datasource["status"] = "loadfailed"
        datasource["message"] = traceback.format_exception_only(sys.exc_type,sys.exc_value)
        traceback.print_exc()
    finally:
        ds = None

def prepareDatasource(datasource):
    datasource["file"] = datasource["file"].strip()
    if (datasource["file"].lower().endswith(".grb")):
        datasource["datasource"] = datasource["file"]
    elif (datasource["file"].lower().endswith(".nc")):
        datasource["datasource"] = datasource["file"]
    elif (datasource["file"].lower().endswith(".nc.gz")):
        fileinfo = os.stat(datasource["file"])
        if datasource.get("datasource"):
            #loaded before
            if os.path.exists(datasource["datasource"]):
                #datsource file exists
                dsinfo = os.stat(datasource["datasource"])
                if fileinfo.st_mtime != dsinfo.st_mtime:
                    #datasource file is older than the compressed datasouce file
                    datasource["datasource"] = None
            else:
                #datasource file exists
                datasource["datasource"] = None
        else:
            #not loaded before
            ds = datasource["file"][:-3]
            if os.path.exists(ds):
                dsinfo = os.stat(ds)
                if fileinfo.st_mtime == dsinfo.st_mtime:
                    #datasource file exists and also has the same modify time as compressed datasource file
                    datasource["datasource"] = ds

        if not datasource.get("datasource"):
            subprocess.check_call(["gzip","-k","-f","-q","-d",datasource["file"]])
            datasource["datasource"] = datasource["file"][:-3]
            os.utime(datasource["datasource"],(fileinfo.st_atime,fileinfo.st_mtime))
            print "Succeed to decompressed file \"{}\" to file \"{}\"".format(datasource["file"],datasource["datasource"])

        if not datasource.get("datasource") or not os.path.exists(datasource["datasource"]):
            raise Exception("Datasource ({}) is missing".format(datasource["datasource"]))
    else:
        raise Exception("Datasource {} is not supported".format(datasource["file"]))

DIRECTIONS_METADATA = {
    4:[360/4,math.floor(360 / 8 * 100) / 100,["N","E","S","W"]],
    8:[360/8,math.floor(360 / 16 * 100) / 100,["N","NE","E","SE","S","SW","W","NW"]],
    16:[360/16,math.floor(360 / 32 * 100) / 100,["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]],
    32:[360/32,math.floor(360 / 64 * 100) / 100,["N","NbE","NNE","NEbN","NE","NEbE","ENE","EbN","E","EbS","ESE","SEbE","SE","SEbS","SSE","SbE","S","SbW","SSW","SWbS","SW","SWbW","WSW","WbS","W","WbN","WNW","NWbW","NW","NWbN","NNW","NbW"]],
}

def getDirFunc(mode):
    mode = mode or 16
    direction_metadata = DIRECTIONS_METADATA[mode]
    def _func(band,data):
        if data:
            index = int((math.floor(data / direction_metadata[0])  + (0 if (round(data % direction_metadata[0] * 100) / 100 <= direction_metadata[1]) else 1) ) % mode)
            #return "{}({})".format(direction_metadata[2][index],"{:-.0f}".format(data))
            return direction_metadata[2][index]
        else:
            return None

    return _func

WEATHER_ICONS = {
    1:{"icon":"/dist/static/images/weather/sunny.png","night-icon":"/dist/static/images/weather/sunny-night.png","desc":"Sunny"},
    2:{"icon":"/dist/static/images/weather/clear.png","desc":"Clear"},
    3:{"icon":"/dist/static/images/weather/partly-cloudy.png","night-icon":"/dist/static/images/weather/partly-cloudy-night.png","desc":"Mostly sunny,Partly cloudy"},
    4:{"icon":"/dist/static/images/weather/cloudy.png","desc":"Cloudy"},
    6:{"icon":"/dist/static/images/weather/hazy.png","night-icon":"/dist/static/images/weather/hazy-night.png","desc":"Hazy"},
    8:{"icon":"/dist/static/images/weather/light-rain.png","desc":"Light rain"},
    9:{"icon":"/dist/static/images/weather/windy.png","desc":"Windy"},
    10:{"icon":"/dist/static/images/weather/fog.png","night-icon":"/dist/static/images/weather/fog-night.png","desc":"Fog"},
    11:{"icon":"/dist/static/images/weather/showers.png","night-icon":"/dist/static/images/weather/showers-night.png","desc":"Shower"},
    12:{"icon":"/dist/static/images/weather/rain.png","desc":"Rain"},
    13:{"icon":"/dist/static/images/weather/dusty.png","desc":"Dusty"},
    14:{"icon":"/dist/static/images/weather/frost.png","desc":"Frost"},
    15:{"icon":"/dist/static/images/weather/snow.png","desc":"Snow"},
    16:{"icon":"/dist/static/images/weather/storm.png","desc":"Storm"},
    17:{"icon":"/dist/static/images/weather/light-showers.png","night-icon":"/dist/static/images/weather/light-showers-night.png","desc":"Light shower"},
    18:{"icon":"/dist/static/images/weather/heavy-showers.png","desc":"Heavy shower"},
    19:{"icon":"/dist/static/images/weather/tropicalcyclone.png","desc":"Cyclone"},
}
def getWeatherIcon(band,data):
    if data is None:
        return None
    icon = WEATHER_ICONS.get(int(data))
    if icon is None:
        return None
    elif band.get("is_night",False):
        return "<img src='{}' style='width:36px;height:34px;' />".format(icon.get("night-icon",icon["icon"]))
    else:
        return "<img src='{}' style='width:36px;height:34px;' />".format(icon["icon"])

def getWeather(band,data):
    if data is None:
        return None
    icon = WEATHER_ICONS.get(int(data))
    if icon is None:
        return None
    else:
        return icon["desc"]

def loadAllDatasources():
    for workspace in raster_datasources:
        for datasourceId in raster_datasources[workspace]:
            try:
                prepareDatasource(raster_datasources[workspace][datasourceId])
            except:
                traceback.print_exc()
                raster_datasources[workspace][datasourceId]["status"] = "notsupport"
                raster_datasources[workspace][datasourceId]["message"] = traceback.format_exception_only(sys.exc_type,sys.exc_value)
                continue
            loadDatasource(raster_datasources[workspace][datasourceId])
        
raster_datasources={
    "bom":{
        "IDW71000_WA_T_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71000_WA_T_SFC.nc.gz"),
            "sort_key":("weather","temperature"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Temp",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:right",
            }
        },
        "IDW71001_WA_Td_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71001_WA_Td_SFC.nc.gz"),
            #"name":"Hourly dew point temperature",
            "sort_key":("weather","other"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Dewpt",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71002_WA_MaxT_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71002_WA_MaxT_SFC.nc.gz"),
            #"name":"Daily maximum temperature",
            "sort_key":("weather","temperature","maximum"),
            "time":"14:00:00",
            "var":"max_temp",
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Max Temp",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71003_WA_MinT_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71003_WA_MinT_SFC.nc.gz"),
            #"name":"Daily minimum temperature",
            "sort_key":("weather","temperature","minimum"),
            "time":"06:00:00",
            "var":"min_temp",
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Min Temp",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71005_WA_DailyPrecip_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71005_WA_DailyPrecip_SFC.nc.gz"),
            #"name":"Daily Precipitation",
            "sort_key":("weather","precipitation"),
            "var":"precip",
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Precip",
                "srs":"EPSG:4326",
                "style":"text-align:center",
                "pattern":"{:-.0f}",
            }
        },
        "IDW71006_WA_Wind_Mag_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71006_WA_Wind_Mag_SFC.nc.gz"),
            #"name":"Wind Speed",
            "sort_key":("weather","wind",10),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Speed",
                "group":"10m Wind",
                "srs":"EPSG:4326",
                "style":"text-align:center",
                "pattern":"{:-.1f}",
            }
        },
        "IDW71013_WA_PoP_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71013_WA_PoP_SFC.nc.gz"),
            #"name":"Probability of 0.2mm Precipitation (3hrly)",
            "sort_key":("weather","precipitation",0.2,"probability"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"0.2mm Precip",
                "srs":"EPSG:4326",
                "style":"text-align:center",
                "pattern":"{:-.1f}",
            }
        },
        "IDW71014_WA_DailyPrecip25Pct_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71014_WA_DailyPrecip25Pct_SFC.nc.gz"),
            #"name":"25% Confidence Precipitation Amount for 24 hours",
            "sort_key":("weather","precipitation","probability",25),
            "var":"precip_25%",
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Precip(25%)",
                "srs":"EPSG:4326",
                "style":"text-align:center",
                "pattern":"{:-.0f}",
            }
        },
        "IDW71015_WA_DailyPrecip50Pct_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71015_WA_DailyPrecip50Pct_SFC.nc.gz"),
            #"name":"50% Confidence Precipitation Amount for 24 hours",
            "sort_key":("weather","precipitation","probability",50),
            "var":"precip_50%",
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Precip(50%)",
                "srs":"EPSG:4326",
                "style":"text-align:center",
                "pattern":"{:-.0f}",
            }
        },
        "IDW71016_WA_DailyPrecip75Pct_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71016_WA_DailyPrecip75Pct_SFC.nc.gz"),
            #"name":"75% Confidence Precipitation Amount for 24 hours",
            "sort_key":("weather","precipitation","probability",75),
            "var":"precip_75%",
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Precip(75%)",
                "srs":"EPSG:4326",
                "style":"text-align:center",
                "pattern":"{:-.0f}",
            }
        },
        "IDW71017_WA_Sky_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71017_WA_Sky_SFC.nc.gz"),
            #"name":"Sky cover",
            "sort_key":("weather","sky"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Sky",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71018_WA_RH_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71018_WA_RH_SFC.nc.gz"),
            #"name":"Hourly relative humidity",
            "sort_key":("weather","relative humidity"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"RH",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71022_WA_WindWaveHgt_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71022_WA_WindWaveHgt_SFC.nc.gz"),
            #"name":"Wind Wave Height",
            "sort_key":("weather","wind",10),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Wind Height",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71023_WA_Swell_Mag_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71023_WA_Swell_Mag_SFC.nc.gz"),
            #"name":"Swell Magnitude",
            "sort_key":("sea","swell"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Magnitude",
                "group":"Swell",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71030_WA_DailyPrecip10Pct_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71030_WA_DailyPrecip10Pct_SFC.nc.gz"),
            #"name":"10% Confidence Precipitation Amount for 24 hours",
            "sort_key":("weather","rainfall","confidence",10),
            "var":"rainfall_10%",
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Precip",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71031_WA_Precip10Pct_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71031_WA_Precip10Pct_SFC.nc.gz"),
            #"name":"10% Confidence Precipitation Amount in 3 Hours",
            "sort_key":("weather","rainfall","confidence",10),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
                "is_night":isNightFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getWeatherIcon,
            },
            "options":{
                "title":"Precip",
                "pattern":"{:-.1f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71032_WA_Precip25Pct_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71032_WA_Precip25Pct_SFC.nc.gz"),
            #"name":"25% Confidence Precipitation Amount in 3 Hours",
            "sort_key":("weather","rainfall","exceeding chance",25),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
                "is_night":isNightFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getWeatherIcon,
            },
            "options":{
                "title":"Precip",
                "pattern":"{:-.1f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71033_WA_Precip50Pct_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71033_WA_Precip50Pct_SFC.nc.gz"),
            #"name":"50% Confidence Precipitation Amount in 3 Hours",
            "sort_key":("weather","rainfall","exceeding chance",50),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
                "is_night":isNightFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getWeatherIcon,
            },
            "options":{
                "title":"Precip",
                "pattern":"{:-.1f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71034_WA_WxIcon_SFC_ICON":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71034_WA_WxIcon_SFC.nc.gz"),
            "name":"3hrly weather icon",
            "sort_key":("weather",),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
                "is_night":isNightFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getWeatherIcon,
            },
            "options":{
                "title":"Weather",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71034_WA_WxIcon_SFC_DESC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71034_WA_WxIcon_SFC.nc.gz"),
            "name":"3hrly weather",
            "sort_key":("weather",),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
                "is_night":isNightFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getWeather,
            },
            "options":{
                "title":"Weather",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71068_WA_ApparentT_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71068_WA_ApparentT_SFC.nc.gz"),
            #"name":"Hourly apparent temperature (deg)",
            "sort_key":("weather","apparent"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Apparent Temp",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71069_WA_SigWaveHgt_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71069_WA_SigWaveHgt_SFC.nc.gz"),
            #"name":"Total Significant Wave Height",
            "sort_key":("sea",),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Sea & Swell",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71071_WA_WindMagKmh_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71071_WA_WindMagKmh_SFC.nc.gz"),
            #"name":"Hourly wind magnitude",
            "sort_key":("weather","wind",10),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Speed",
                "group":"10m Wind",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71072_WA_WindGustKmh_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71072_WA_WindGustKmh_SFC.nc.gz"),
            #"name":"Wind gust",
            "sort_key":("weather","wind",10),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Gust",
                "group":"10m Wind",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71089_WA_Wind_Dir_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71089_WA_Wind_Dir_SFC.nc.gz"),
            #"name":"Hourly wind direction",
            "sort_key":("weather","wind",10),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getDirFunc(16),
            },
            "options":{
                "title":"Dir",
                "group":"10m Wind",
                #"pattern":"{:-.2f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71090_WA_DailyPoP_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71090_WA_DailyPoP_SFC.nc.gz"),
            #"name":"Daily probability of precipitation",
            "sort_key":("weather","precipitation","probability"),
            "var" :"precip_chance",
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getDirFunc(16),
            },
            "options":{
                "title":"Precip",
                "pattern":"{:-.1f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71092_WA_Swell_Dir_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71092_WA_Swell_Dir_SFC.nc.gz"),
            #"name":"Swell Direction",
            "sort_key":("sea","swell"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getDirFunc(16),
            },
            "options":{
                "title":"Dir",
                "group":"Swell",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71094_WA_WxThunderstorms_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71094_WA_WxThunderstorms_SFC.nc.gz"),
            "name":"3 hourly weather - thunderstorms",
            "sort_key":("weather","other"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Thunderstorms",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71096_WA_WxPrecipitationFrozen_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71096_WA_WxPrecipitationFrozen_SFC.nc.gz"),
            "name":"3 hourly weather - frozen precipitation",
            "sort_key":("weather","other"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Frozen Precip",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71097_WA_WxPrecipitation_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71097_WA_WxPrecipitation_SFC.nc.gz"),
            "name":"3 hourly weather - precipitation",
            "sort_key":("weather","other"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Precip",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71102_WA_WxFog_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71102_WA_WxFog_SFC.nc.gz"),
            "name":"3 hourly weather - fog",
            "sort_key":("weather","other"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Fog",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71107_WA_WxFrost_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71107_WA_WxFrost_SFC.nc.gz"),
            "name":"3 hourly weather - frost",
            "sort_key":("weather","other"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Frost",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71109_WA_MixHgt_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71109_WA_MixHgt_SFC.nc.gz"),
            #"name":"3 hourly mixing height (m)",
            "sort_key":("weather","other"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Mixing Height",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71110_WA_WindMagKmh_1500mAMSL":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71110_WA_WindMagKmh_1500mAMSL.nc.gz"),
            #"name":"3 hourly wind magnitude at 1500m above mean sea level (km/h)",
            "sort_key":("weather","wind",1500),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Speed",
                "group":"1500m Wind",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71111_WA_Wind_Dir_1500mAMSL":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71111_WA_Wind_Dir_1500mAMSL.nc.gz"),
            #"name":"3 hourly wind direction at 1500m above mean sea level",
            "sort_key":("weather","wind",1500),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getDirFunc(16),
            },
            "options":{
                "title":"Dir",
                "group":"1500m Wind",
                #"pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71112_WA_WindMagKmh_3000mAMSL":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71112_WA_WindMagKmh_3000mAMSL.nc.gz"),
            #"name":"3 hourly wind magnitude at 3000m above mean sea level (km/h)",
            "sort_key":("weather","wind",3000),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Speed",
                "group":"3000m Wind",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71113_WA_Wind_Dir_3000mAMSL":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71113_WA_Wind_Dir_3000mAMSL.nc.gz"),
            #"name":"3 hourly wind direction at 3000m above mean sea level",
            "sort_key":("weather","wind",3000),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getDirFunc(16),
            },
            "options":{
                "title":"Dir",
                "group":"3000m Wind",
                #"pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71114_WA_LAL2_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71114_WA_LAL2_SFC.nc.gz"),
            #"name":"3 hourly thunderstorm activity level",
            "sort_key":("weather","other"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Thunderstorm Activity Level",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71115_WA_CHaines_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71115_WA_CHaines_SFC.nc.gz"),
            #"name":"3 hourly continuous Haines",
            "sort_key":("weather","other"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Continuous Haines",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71116_WA_MaxFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71116_WA_MaxFDI_SFC.nc.gz"),
            #"name":"Daily maximum fire danger index",
            "sort_key":("bushfire",),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Fire Danger Index",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71117_WA_FFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71117_WA_FFDI_SFC.nc.gz"),
            #"name":"Hourly forest fire danger index",
            "sort_key":("bushfire",'forest',"ffdi"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"FFDI",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71118_WA_MaxFFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71118_WA_MaxFFDI_SFC.nc.gz"),
            #"name":"Daily maximum forest fire danger index",
            "sort_key":("bushfire",'forest',"ffdi"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Maximum FFDI",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71119_WA_Hrs50FFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71119_WA_Hrs50FFDI_SFC.nc.gz"),
            #"name":"Number of hours FFDI exceeds 50",
            "sort_key":("bushfire",'forest',"ffdi","hours",50),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Hours FFDI exceeds 50",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71120_WA_Hrs75FFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71120_WA_Hrs75FFDI_SFC.nc.gz"),
            #"name":"Number of hours FFDI exceeds 75",
            "sort_key":("bushfire",'forest',"ffdi","hours",75),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Hours FFDI exceeds 75",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71121_WA_Hrs100FFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71121_WA_Hrs100FFDI_SFC.nc.gz"),
            #"name":"Number of hours FFDI exceeds 100",
            "sort_key":("bushfire",'forest',"ffdi","hours",100),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Hours FFDI exceeds 100",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71122_WA_GFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71122_WA_GFDI_SFC.nc.gz"),
            #"name":"Hourly grassland fire danger index",
            "sort_key":("bushfire","grassland","gfdi"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"GFDI",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71123_WA_MaxGFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71123_WA_MaxGFDI_SFC.nc.gz"),
            #"name":"Daily maximum grassland fire danger index",
            "sort_key":("bushfire","grassland","gfdi"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"GFDI",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71124_WA_Hrs50GFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71124_WA_Hrs50GFDI_SFC.nc.gz"),
            #"name":"Number of hours GFDI exceeds 50",
            "sort_key":("bushfire","grassland","gfdi","hours",50),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Hours GFDI exceeds 50",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71125_WA_Hrs75GFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71125_WA_Hrs75GFDI_SFC.nc.gz"),
            #"name":"Number of hours GFDI exceeds 75",
            "sort_key":("bushfire","grassland","gfdi","hours",75),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Hours GFDI exceeds 75",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71126_WA_Hrs100GFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71126_WA_Hrs100GFDI_SFC.nc.gz"),
            #"name":"Number of hours GFDI exceeds 100",
            "sort_key":("bushfire","grassland","gfdi","hours",100),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Hours GFDI exceeds 100",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71127_WA_DF_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71127_WA_DF_SFC.nc.gz"),
            #"name":"Drought factor",
            "sort_key":("bushfire",),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"DF",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71132_WA_Hrs32GFDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71132_WA_Hrs32GFDI_SFC.nc.gz"),
            #"name":"Number of hours GFDI exceeds 32",
            "sort_key":("bushfire","grassland","gfdi","hours",32),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Hours GFDI exceeds 32",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71139_WA_Curing_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71139_WA_Curing_SFC.nc.gz"),
            #"name":"Grassland curing index",
            "sort_key":("bushfire","grassland"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Curing",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71144_WA_GrassFuelLoad_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71144_WA_GrassFuelLoad_SFC.nc.gz"),
            #"name":"Grassland fuel load (t/ha)",
            "sort_key":("bushfire","grassland"),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Fuel Load",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71147_WA_KBDI_SFC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71147_WA_KBDI_SFC.nc.gz"),
            #"name":"Keetch-Byram Drought Index (Observed)",
            "sort_key":("bushfire",),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"KBDI",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71152_WA_DailyWxIcon_SFC_ICON":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71152_WA_DailyWxIcon_SFC.nc.gz"),
            "name":"Daily weather icon",
            "sort_key":("weather",),
            "time":"12:00:00",
            "var":"weather_icon",
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getWeatherIcon,
            },
            "options":{
                "title":"Weather",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71152_WA_DailyWxIcon_SFC_DESC":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71152_WA_DailyWxIcon_SFC.nc.gz"),
            "name":"Daily weather",
            "sort_key":("weather",),
            "time":"12:00:00",
            "var":"weather",
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getWeather,
            },
            "options":{
                "title":"Weather",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71199_WA_WindMagKmh_1000mAMSL":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71199_WA_WindMagKmh_1000mAMSL.nc.gz"),
            "sort_key":("weather","wind",1000),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
            },
            "options":{
                "title":"Speed",
                "group":"1000m Wind",
                "pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
        "IDW71200_WA_Wind_Dir_1000mAMSL":{
            "file":os.path.join(Setting.getString("BOM_HOME","/var/www/bom_data"),"adfd","IDW71200_WA_Wind_Dir_1000mAMSL.nc.gz"),
            "sort_key":("weather","wind",1000),
            "metadata_f":{
                "refresh_time":getEpochTimeFunc("NETCDF_DIM_time",1),
                "band_timeout":getBandTimeoutFunc("NETCDF_DIM_time"),
                "name":getMetadataFunc("long_name",1),
                "unit":getUnitFunc("units",1),
            },
            "band_metadata_f":{
                "start_time":getEpochTimeFunc("NETCDF_DIM_time"),
            },
            "band_f":{
                "band_match":isInBandFunc,
                "data_map":getDirFunc(16),
            },
            "options":{
                "title":"Dir",
                "group":"1000m Wind",
                #"pattern":"{:-.0f}",
                "srs":"EPSG:4326",
                "style":"text-align:center",
            }
        },
    }
}

def getRasterBands(datasource,bandids,bandMatchFunc):
    """
    datasource: the loading meta data of  raster datasource
    bandIds: a list of band ids, each member of list can be a id or list of ids
    batchMatchFunc: the function to check whether the band match the specified bandid
    return the ranster band with same structure as bandIds
    """
    bands = []
    for bandid in bandids:
        if isinstance(bandid,list):
            bands.append(getRasterBands(datasource,bandid,bandMatchFunc))
        else:
            matchedBand = None
            for band in datasource["bands"]:
                if bandMatchFunc(datasource,band,bandid):
                    matchedBand = band
                    break
            bands.append(matchedBand)
    return bands

def getBandsData(datasource,bands,pixel,mapFunc=None):
    """
    datasource: raster datasource
    bands: The bands
    pixel: the position which data will be extracted
    mapFunc:tansform the data
    """
    datas = []
    for band in bands:
        if isinstance(band,list):
            datas.append(getBandsData(datasource,band,pixel,mapFunc))
        else:
            data = None
            if band is None:
                data = None
            elif band["index"] < 1 or band["index"] > datasource.RasterCount:
                data = None
            elif not pixel:
                data = None
            else:
                ds_band = datasource.GetRasterBand(band["index"])
                if ds_band is not None:
                    structval = ds_band.ReadRaster(pixel[0], pixel[1], 1, 1, buf_type=gdal.GDT_Float32) 
                else:
                    structval = None
                if structval:
                    data = struct.unpack('f', structval)[0]
                    if data == ds_band.GetNoDataValue():
                        data = None
                else:
                    data = None
            if data is None:
                datas.append([band["index"] if band else -1,data])
            elif mapFunc:
                datas.append([band["index"] if band else -1 ,mapFunc(band,data)])
            else:
                datas.append([band["index"] if band else -1,data])
    return datas

def formatData(data,pattern,no_data=None):
    if not data:
        return no_data
    elif pattern:
        if isinstance(data,datetime.datetime) or isinstance(data,datetime.date) or isinstance(data,datetime.time) or isinstance(data,datetime.timedelta):
            return data.strftime(pattern)
        else:
            return pattern.format(data)
    else:
        return str(data)

def formatContext(context,patterns):
    for key,value in context.iteritems():
        if isinstance(value,datetime.datetime):
            context[key] = formatData(value,patterns.get("{}_pattern".format(key),patterns.get("datetime_pattern")),"")
        elif isinstance(value,datetime.date):
            context[key] = formatData(value,patterns.get("{}_pattern".format(key),patterns.get("date_pattern")),"")
        elif isinstance(value,datetime.time):
            context[key] = formatData(value,patterns.get("{}_pattern".format(key),patterns.get("time_pattern")),"")
        elif isinstance(value,datetime.timedelta):
            context[key] = formatData(value,patterns.get("{}_pattern".format(key),patterns.get("timedelta_pattern")),"")
        
def formatBandsData(datasource,noData="",bandsData = None):
    if bandsData is None:
        bandsData = datasource["data"]
    index = 0;
    while index < len(bandsData):
        if isinstance(bandsData[index],list) and ((len(bandsData[index]) != 2) or isinstance(bandsData[index][0],list)):
            formatBandsData(datasource,noData,bandsData[index])
        elif bandsData[index] is not None:
            bandsData[index][1] = formatData(bandsData[index][1],datasource["options"].get("pattern"),noData)
        index += 1

def getRasterData(options):
    """
    options: a dictionary
        datasource: the raster datasource
        point: the point whose data will retrieved from datasource bands, optional
        srs: point srs  optional
        pixel: the pxiel whose data will be retireved from datasource bands, optional
        band_indexes: the list of band index,optional or the list of list band index
        bandids: the list of band id,optional, ot the list of list band id

    Return dictionary
        status: true if succeed;otherwise false
        message: error message if failed
        datas: data of bands, if succeed
    """
    ds = None
    try:
        if not options.get("datasource"):
            raise Exception("Datasource is missing in the options")

        if not raster_datasources.get(options["datasource"]["workspace"]):
            raise Exception("Workspace '{}' is not found".format(options["datasource"]["workspace"]))

        if not raster_datasources[options["datasource"]["workspace"]].get(options["datasource"]["id"]):
            raise Exception("Datasource '{}:{}' is not found".format(options["datasource"]["workspace"],options["datasource"]["id"]))

        if not options.get("pixel") and not options.get("point"):
            raise Exception("Either pixel or point must be present in the options")

        if not options.get("band_indexes") and not options.get("bandids"):
            raise Exception("Either band_indexes or bandids must be present in the options")

        datasource = raster_datasources[options["datasource"]["workspace"]][options["datasource"]["id"]]
        if datasource["status"] == "notsupport":
            raise Exception(datasource["message"])

        options["datasource"]["context"] = {}
        runtimes = 0
        while True:
            runtimes += 1
            prepareDatasource(datasource)
            ds = gdal.Open(datasource["datasource"])
            if datasource.get('status') == 'loaded':
                if datasource["metadata_f"]["refresh_time"](ds)  != datasource["metadata"]["refresh_time"]:
                    datasource["status"]="outdated"

            #try to reload datasource if required
            while (datasource.get('status') or "loadfailed") != "loaded":
                if (datasource.get('status') or 'loadfailed') in ("loadfailed","outdated"):
                    loadDatasource(datasource)
                    if (datasource.get('status') or 'loadfailed') == "loadfailed":
                        raise Exception(datasource.get("message") or "unknown error.")
                else:
                    #loading by other threads, wait
                    time.sleep(0.1)

            bands = None
            if options.get("band_indexes"):
                bands = getRasterBands(datasource,options["band_indexes"],lambda datasource,band,band_index:band["index"] == band_index)
            else:
                bands = getRasterBands(datasource,options["bandids"],datasource["band_f"]["band_match"])

            try:
                if not options.get("pixel"):
                    if options.get("point"):
                        point = ogr.Geometry(ogr.wkbPoint)
                        point.AddPoint(options["point"][0],options["point"][1])
                        point.Transform(osr.CoordinateTransformation(getEpsgSrs(options["srs"]),datasource["srs"]))
                        # Convert geographic co-ordinates to pixel co-ordinates
                        forward_transform = Affine.from_gdal(*ds.GetGeoTransform())
                        reverse_transform = ~forward_transform
                        px, py = reverse_transform * (point.GetX(),point.GetY())
                        #choose the cloest pixel
                        px, py = int(px + 0.5), int(py + 0.5)
                        if px < 0 or px > ds.RasterXSize or py < 0 or py > ds.RasterYSize:
                            options["pixel"] = None
                        else:
                            options["pixel"] = (px,py)

                # Extract pixel value
                datas = getBandsData(ds,bands,options["pixel"],datasource["band_f"]["data_map"] if datasource["band_f"].get("data_map") else None)

                #import ipdb;ipdb.set_trace()
                options["datasource"]["status"] = True
                options["datasource"]["data"] = datas
                return options["datasource"]
            except:
                #retrieve data failed, maybe be caused by ftp sync process; retrieved it again
                if runtimes == 1:
                    ds = None
                    ds = gdal.Open(datasource["datasource"])
                else:
                    raise
    except:
        traceback.print_exc()
        options["datasource"]["status"] = False
        options["datasource"]["message"] = traceback.format_exception_only(sys.exc_type,sys.exc_value)
        return options["datasource"]
    finally:
        if datasource and options["datasource"] and "context" in options["datasource"]:
            options["datasource"]["context"].update(datasource["metadata"])
        ds = None


request_options={
    "no_data":"-",
    "datetime_pattern":"%d/%m/%Y %H:%M:%S",
    "refresh_time_pattern":"%d/%m %H:%M",
}
forecast_options={
    "time_pattern":"%H:%M",
    "date_pattern":"%A %d %B",
    "forecast_time_pattern":"%H:%M",
    "forecast_date_pattern":"%d/%m/%Y",
    "time_style":"text-align:center;white-space:nowrap;",
    "date_style":"text-align:left"
}

def setDefaultOptionIfMissing(options,defaultOptions):
    """
    If options is none or empty, return defaultOptions directly;
    Otherwise set option in options if option exist in defaultOptions but does not exist in options.
    """
    if not defaultOptions:
        return {} if options is None else options

    if not options:
        return dict(defaultOptions)

    for key,value in defaultOptions.iteritems():
        if key not in options:
            options[key] = value

    return options


@bottle.route('/forecastmetadata',method="GET")
def forecastmetadata():
    """
    Get forecast metadata
    """
    bottle.response.set_header("Content-Type", "application/json")
    return forecast_metadata


@bottle.route('/spotforecast/<fmt>',method="POST")
def spotforecast(fmt):
    """
    Get data from raster datasources
    Request datas
        point: the coordinate of the point whose data will be retrieved from raster datasources
        srs: the spatial reference system of the coordinate, if missing, epsg:4326 will be used
        datasources:  raster datasources and related options
          {
            workspace: the workspace of the datasource; for example:bom
            {
                datasource : bands(a band identity or a array of band identities; its value dependents on workspace).
            }
          {
    Response: json or html
        {
            workspace: 
            {
                datasource:  
                {
                    status:true/false
                    message: error message if failed
                    data: a array of data retrieved from band; null represent no value or invalid band. datas has the same length as bands
                }
            }

        }
    """
    fmt = (fmt or "json").lower()
    try:
        requestData = bottle.request.forms.get("data")
        if requestData:
            requestData = json.loads(requestData)
        else:
            requestData = {}
        #check whether request is valid and initialize the request parameters
        requestData["srs"] = (requestData.get("srs") or "EPSG:4326").strip().upper()
        
        if not requestData.get("forecasts"):
            raise Exception("Parameter 'forecasts' is missing")

        if not requestData.get("point"):
            raise Exception("Parameter 'point' is missing.")

        for forecast in requestData["forecasts"]:
            #initialize 'days' parameter
            if not forecast.get("days"):
                raise Exception("Parameter 'days' is missing.")
            elif not isinstance(forecast["days"],list):
                forecast["days"] = [forecast["days"]]

            #initialize 'times' parameter
            if not forecast.get("times"):
                raise Exception("Parameter 'times' is  missing.")
            elif not isinstance(forecast["times"],list):
                forecast["times"] = [forecast["times"]]

            #format parameter 'times' to a 2 dimension array of datatime object;the first dimension is day, the second dimension is times in a day
            forecast["times"] = [[datetime.datetime.strptime("{} {}".format(day,time),"%Y-%m-%d %H:%M:%S").replace(tzinfo=PERTH_TIMEZONE) for time in forecast["times"]] for day in forecast["days"]]

            if not forecast.get("times_data"):
                raise Exception("Parameter 'times_data' is missing.")
                

            #forecast["times"] = [datetime.datetime.strptime(dt,"%Y-%m-%d %H:%M:%S").replace(tzinfo=PERTH_TIMEZONE)  for dt in forecast["times"]]

            if not isinstance(forecast["times_data"],list):
                forecast["times_data"] = [forecast["times_data"]]
            #initialize 'times_data' parameter
            for datasource in forecast["times_data"]:
                if datasource.get("group"):
                    if not datasource.get("datasources"):
                        raise Exception("Property 'datasources' of group in times_data is missing.")
                    for ds in datasource["datasources"]:
                        if not ds.get("workspace"):
                            raise Exception("Property 'workspace' of datasource in times_data's group is missing.")
                        if not ds.get("id"):
                            raise Exception("Property 'id' of datasource in times_data's group is missing.")
                        if ds.get("times"):
                            if not isinstance(ds["times"],list):
                                ds["times"] = [ds["times"]]
                            if len(ds["times"]) != len(forecast["times"]):
                                raise Exception("The length of times of datasource in times_data's group is not equal with the length of times of forecast")
                            ds["times"] = [[datetime.datetime.strptime("{} {}".format(day,time),"%Y-%m-%d %H:%M:%S").replace(tzinfo=PERTH_TIMEZONE) for time in ds["times"]] for day in forecast["days"]]


                else:
                    if not datasource.get("workspace"):
                        raise Exception("Property 'workspace' of datasource in times_data is missing.")
                    if not datasource.get("id"):
                        raise Exception("Property 'id' of datasource in times_data is missing.")
                    if datasource.get("times"):
                        if not isinstance(datasource["times"],list):
                            datasource["times"] = [datasource["times"]]
                        if len(datasource["times"]) != len(forecast["times"]):
                            raise Exception("The length of times of datasource in times_data is not equal with the length of times of forecast")
                        datasource["times"] = [[datetime.datetime.strptime("{} {}".format(day,time),"%Y-%m-%d %H:%M:%S").replace(tzinfo=PERTH_TIMEZONE) for time in datasource["times"]] for day in forecast["days"]]

            #initialize 'daily_data' parameter
            if forecast.get("daily_data"):
                for datasource in forecast["daily_data"].itervalues():
                    if not datasource.get("workspace"):
                        raise Exception("Property 'workspace' of datasource in daily_data is missing.")
                    if not datasource.get("id"):
                        raise Exception("Property 'id' of datasource in daily_data is missing.")
                    datasourceMetadata = raster_datasources.get(datasource["workspace"],{}).get(datasource["id"],{})
                    datasource["times"] = [datetime.datetime.strptime("{} {}".format(day,datasourceMetadata.get("time","00:00:00")),"%Y-%m-%d %H:%M:%S").replace(tzinfo=PERTH_TIMEZONE)  for day in forecast["days"]]

            #format the days to a array of datetime object
            forecast["days"] = [datetime.datetime.strptime(day,"%Y-%m-%d").replace(tzinfo=PERTH_TIMEZONE)  for day in forecast["days"]]

        #extract the data from raster dataset and save the data into 'data' property of each datasource
        #the data structure is the same as the times structure
        for forecast in requestData["forecasts"]:
            for datasource in forecast.get("daily_data",{}).itervalues():
                datasource.update(getRasterData({
                    "datasource":datasource,
                    "point":requestData["point"],
                    "srs":requestData["srs"],
                    "bandids":datasource["times"]
                }))

            for datasource in forecast.get("times_data",[]):
                if datasource.get("group"):
                    for ds in datasource["datasources"]:
                        ds.update(getRasterData({
                            "datasource":ds,
                            "point":requestData["point"],
                            "srs":requestData["srs"],
                            "bandids":datasource.get("times",forecast["times"])
                        }))
                else:
                    datasource.update(getRasterData({
                        "datasource":datasource,
                        "point":requestData["point"],
                        "srs":requestData["srs"],
                        "bandids":forecast["times"]
                    }))
    
        result = requestData
        result["issued_time"] = datetime.datetime.now(PERTH_TIMEZONE)

        if fmt == "json":
            bottle.response.set_header("Content-Type", "application/json")
            return result
        else:
            #html
            #get total columns and check whether have groups
            for forecast in result["forecasts"]:
                forecast["has_group"] = False
                forecast["has_daily_group"] = True
                forecast["columns"] = 1
                for datasource in forecast.get("times_data",[]):
                    if datasource.get("group"):
                        forecast["has_group"] = True
                        datasource["columns"] = 0
                        for ds in datasource["datasources"]:
                            forecast["columns"] += 1
                            datasource["columns"] += 1
                            ds["title"] = ds.get("title") or ds["id"]
                    else:
                        forecast["columns"] += 1
                        datasource["title"] = datasource.get("title") or datasource["id"]
                if len(forecast.get("daily_data",{})) == 0 and len(forecast["times"][0]) < 2:
                   forecast["has_daily_group"] = False
    
            #prepare the format options
            result["options"] = setDefaultOptionIfMissing(result.get("options"),request_options)

            for forecast in requestData["forecasts"]:
                forecast["options"] = setDefaultOptionIfMissing(forecast.get("options"),forecast_options)
                for datasource in forecast.get("daily_data",{}).itervalues():
                    try:
                        datasource["options"] = setDefaultOptionIfMissing(datasource.get("options"),raster_datasources[datasource["workspace"]][datasource["id"]].get("options"))
                    except:
                        pass

                for datasource in forecast.get("times_data",[]):
                    if datasource.get("group"):
                        for ds in datasource["datasources"]:
                            try:
                                ds["options"] = setDefaultOptionIfMissing(ds.get("options"),raster_datasources[ds["workspace"]][ds["id"]].get("options"))
                            except:
                                pass
                    else:
                        try:
                            datasource["options"] = setDefaultOptionIfMissing(datasource.get("options"),raster_datasources[datasource["workspace"]][datasource["id"]].get("options"))
                        except:
                            pass


            #format data if required
            for forecast in result["forecasts"]:
                #format time column
                index = 0;
                while index < len(forecast["days"]):
                    timeIndex = 0
                    while timeIndex < len(forecast["times"][index]):
                        if forecast.get("has_daily_group"):
                           forecast["times"][index][timeIndex] = formatData(forecast["times"][index][timeIndex],forecast["options"].get("forecast_time_pattern"),result["options"].get("no_data") or "")
                        else:
                           forecast["times"][index][timeIndex] = formatData(forecast["times"][index][timeIndex],forecast["options"].get("forecast_date_pattern"),result["options"].get("no_data") or "")
                        timeIndex += 1
                    index += 1
                
                #format daily data
                for datasource in forecast.get("daily_data", {}).itervalues():
                    if datasource["status"] :
                        formatBandsData(datasource,result["options"].get("no_data") or "")
                
                #generate daily group row data
                if forecast.get("has_daily_group"):
                    forecast["daily_group"] = []
                    groupContext = {}
                    index = 0
                    while index < len(forecast["days"]):
                        groupContext["date"] = forecast["days"][index].strftime(forecast["options"]["date_pattern"])
                        for name,datasource in forecast.get("daily_data",[]).iteritems():
                            groupContext[name] = datasource["data"][index][1]
                        forecast["daily_group"].append(forecast.get("options",{}).get("daily_title_pattern","{date}").format(**groupContext))
                        index += 1
                
                #format times data
                for datasource in forecast.get("times_data",[]):
                    if datasource.get("group"):
                        for ds in datasource["datasources"]:
                            if ds.get("context"):
                                formatContext(ds["context"],result["options"])
                                ds["options"]["title"] = ds["options"]["title"].format(**ds["context"])
                                if raster_datasources[ds["workspace"]][ds["id"]].get("metadata",{}).get("unit"):
                                    ds["options"]["title"] = "{}<br>({})".format(ds["options"]["title"],raster_datasources[ds["workspace"]][ds["id"]]["metadata"]["unit"])

                            if ds["status"]:
                                formatBandsData(ds,result["options"].get("no_data") or "")
                    else:
                        if datasource.get("context"):
                            formatContext(datasource["context"],result["options"])
                            datasource["options"]["title"] = datasource["options"]["title"].format(**datasource["context"])
                            if raster_datasources[datasource["workspace"]][datasource["id"]].get("metadata",{}).get("unit"):
                                datasource["options"]["title"] = "{}<br>({})".format(datasource["options"]["title"],raster_datasources[datasource["workspace"]][datasource["id"]]["metadata"]["unit"])

                        if datasource["status"] :
                            formatBandsData(datasource,result["options"].get("no_data") or "")

            bottle.response.set_header("Content-Type", "text/html")
            return bottle.template('spotforecast.html',template_adapter=bottle.Jinja2Template,template_settings=jinja2settings, staticService=STATIC_SERVICE,data=result,envType=ENV_TYPE)

    except:
        bottle.response.status = 400
        bottle.response.set_header("Content-Type","text/plain")
        traceback.print_exc()
        return traceback.format_exception_only(sys.exc_type,sys.exc_value)
        

    
#load all raster datasource first
loadAllDatasources()
#load forecast metadata
forecast_metadata = {'size':len(raster_datasources["bom"]),'datasources':[]}
for key,value in raster_datasources["bom"].iteritems():
    data = dict(value)
    data.pop("metadata_f")
    data.pop("band_metadata_f")
    data.pop("band_f")
    data.pop("bands")
    data.pop("datasource")
    data.pop("file")
    data["workspace"] = "bom"
    bandTimeout = int(math.ceil(data.get("metadata",{}).get("band_timeout",0) / 3600))
    if bandTimeout >= 24:
        data["type"] = "Daily"
    elif bandTimeout == 1:
        data["type"] = "Hourly"
    elif bandTimeout > 1:
        data["type"] = "{}hrly".format(bandTimeout)
    else:
        data["type"] = None
    data["id"] = key
    forecast_metadata["datasources"].append(data)

sort_key_map={
    "weather":100,
    "sea":200,
    "bushfire":300,
    "temperature":100,
    "other":-1000
}
def _compare_datasource(ds1,ds2):
    index = 0
    length = len(ds1["sort_key"]) if len(ds1["sort_key"]) <= len(ds2["sort_key"]) else len(ds2["sort_key"])
    while index < length:
        key1 = sort_key_map.get(ds1["sort_key"][index])
        key2 = sort_key_map.get(ds2["sort_key"][index])
        if key1 is not None:
            if key2 is not None:
                key1 = 10000000 + int(math.fabs(key1))
                key2 = 10000000 + int(math.fabs(key2))
            else:
                return -1 if key1 > 0 else 1
        elif key2 is not None:
            return 1 if key2 > 0 else -1
        else:
            key1 = ds1["sort_key"][index]
            key2 = ds2["sort_key"][index]

        if key1 == key2:
            pass
        elif key1 < key2:
            return -1
        else:
            return 1
        
        index += 1

    if len(ds1["sort_key"]) == len(ds2["sort_key"]):
        pass
    elif len(ds1["sort_key"]) < len(ds2["sort_key"]):
        return -1
    else:
        return 1

    timeout1 = ds1.get("metadata",{}).get("band_timeout",0)
    timeout2 = ds2.get("metadata",{}).get("band_timeout",0)
    if timeout1 == timeout2:
        pass
    elif timeout1 < timeout2:
        return 1
    else:
        return -1

    name1 = ds1.get("name","")
    name2 = ds2.get("name","")
    if name1 == name2:
        return 0
    elif name1 < name2:
        return 1
    else:
        return -1
    

forecast_metadata["datasources"] = sorted(forecast_metadata["datasources"],cmp=_compare_datasource)
for ds in forecast_metadata["datasources"]:
    ds.pop("sort_key")

