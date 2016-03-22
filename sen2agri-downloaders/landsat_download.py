#! /usr/bin/env python
# -*- coding: iso-8859-1 -*-
"""
    Landsat Data download from earth explorer. Original source code from Olivier Hagolle
    https://github.com/olivierhagolle/LANDSAT-Download
    Incorporates jake-Brinkmann improvements
"""

import glob,os,sys,math,urllib2,urllib,time,math,shutil
import socket
import subprocess

import datetime
import csv
import signal
import osgeo.ogr as ogr
import osgeo.osr as osr
from sen2agri_common_db import *

general_log_path = "/tmp/"
general_log_filename = "landsat_download.log"

#############################################################################
# CONSTANTS
MONTHS_FOR_REQUESTING_AFTER_SEASON_FINSIHED = int(1)
DEBUG = True

#############################"Connection to Earth explorer with proxy

def connect_earthexplorer_proxy(proxy_info,usgs):
     print "Establishing connection to Earthexplorer with proxy..."
     # contruction d'un "opener" qui utilise une connexion proxy avec autorisation
     proxy_support = urllib2.ProxyHandler({"http" : "http://%(user)s:%(pass)s@%(host)s:%(port)s" % proxy_info,
     "https" : "http://%(user)s:%(pass)s@%(host)s:%(port)s" % proxy_info})
     opener = urllib2.build_opener(proxy_support, urllib2.HTTPCookieProcessor)

     # installation
     urllib2.install_opener(opener)

     # parametres de connection
     params = urllib.urlencode(dict(username=usgs['account'], password=usgs['passwd']))

     # utilisation
     f = opener.open('https://ers.cr.usgs.gov/login', params)
     data = f.read()
     f.close()

     if data.find('You must sign in as a registered user to download data or place orders for USGS EROS products')>0 :
        print "Authentification failed"
        sys.exit(-1)

     return


#############################"Connection to Earth explorer without proxy

def connect_earthexplorer_no_proxy(usgs):
     global general_log_path
     global general_log_filename
     log(general_log_path, "Establishing connection to Earthexplorer...", general_log_filename)
     opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())
     urllib2.install_opener(opener)
     params = urllib.urlencode(dict(username=usgs['account'],password= usgs['passwd']))
     f = opener.open("https://ers.cr.usgs.gov/login", params)
     data = f.read()
     f.close()
     if data.find('You must sign in as a registered user to download data or place orders for USGS EROS products')>0 :
          log(general_log_path, "Authentification failed !", general_log_filename)
          sys.exit(-1)
     return

#############################

def sizeof_fmt(num):
    for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0
#############################
def downloadChunks(url, rep, prod_name, prod_date, abs_prod_path, aoiContext, db):

  """ Downloads large files in pieces
   inspired by http://josh.gourneau.com
  """
  global g_exit_flag
  nom_fic = prod_name + ".tgz"
  print("INFO START")
  print("url: {}".format(url))
  print("rep: {}".format(rep))
  print("nom_fic: {}".format(nom_fic))
  print("INFO STOP")
  log(rep, "Trying to download {0}".format(nom_fic), general_log_filename)
  try:
    req = urllib2.urlopen(url, timeout=600)
    #taille du fichier
    if (req.info().gettype()=='text/html'):
      log(rep, 'Error: the file has a html format for '.format(nom_fic), general_log_filename)
      lignes=req.read()
      if lignes.find('Download Not Found') > 0 :
           return False
      else:
          log(rep, lignes, general_log_filename)
          log(rep, 'Download not found for '.format(nom_fic), general_log_filename)
	  return False
    total_size = int(req.info().getheader('Content-Length').strip())

    if (total_size<50000):
       log(rep, "Error: The file is too small to be a Landsat Image: {0}".format(nom_fic), general_log_filename)
       log(rep, "The used url which generated this error was: {}".format(url), general_log_filename)
       return False

    log(rep, "The filename {} has a total size of {}".format(nom_fic,total_size), general_log_filename)

    total_size_fmt = sizeof_fmt(total_size)
    fullFilename = rep+'/'+nom_fic
    if os.path.isfile(fullFilename) and os.stat(fullFilename).st_size == total_size:
        log(rep, "downloadChunks:File {} already downloaded, returning true".format(fullFilename), general_log_filename)
        return True

    # insert the product name into the downloader_history                                              
    if not db.upsertLandsatProductHistory(aoiContext.siteId, prod_name, DATABASE_DOWNLOADER_STATUS_DOWNLOADING_VALUE, prod_date, abs_prod_path, aoiContext.maxRetries):
         log(rep, "Couldn't upsert into database with status DOWNLOADING for {}".format(prod_name), general_log_filename)
         return False

    downloaded = 0
    CHUNK = 1024 * 1024 *8
    with open(rep+'/'+nom_fic, 'wb') as fp:
        start = time.clock()
        log(rep, 'Downloading {0} ({1})'.format(nom_fic, total_size_fmt), general_log_filename)
	while True and not g_exit_flag:
	     chunk = req.read(CHUNK)
	     downloaded += len(chunk)
	     done = int(50 * downloaded / total_size)
	     sys.stdout.write('\r[{1}{2}]{0:3.0f}% {3}ps'
                             .format(math.floor((float(downloaded)
                                                 / total_size) * 100),
                                     '=' * done,
                                     ' ' * (50 - done),
                                     sizeof_fmt((downloaded // (time.clock() - start)) / 8)))
	     sys.stdout.flush()
	     if not chunk: break
	     fp.write(chunk)
             if g_exit_flag:
                  log(rep, "SIGINT signal caught", general_log_filename)
                  sys.exit(0)
  except socket.timeout, e:
       log(rep, "Timeout for file {0} ".format(nom_fic), general_log_filename)
       return False
  except socket.error, e:
       log(rep, "socket.error for file {0}. Error: {1}".format(nom_fic, e), general_log_filename)
       return False
  except urllib2.HTTPError, e:
       if e.code == 500:
            log(rep, "File doesn't exist: {0}".format(nom_fic), general_log_filename)
       else:
            log(rep, "HTTP Error for file {0}. Error code: {1}. Url: {2}".format(nom_fic, e.code, url), general_log_filename)
       return False
  
  except urllib2.URLError, e:
       log(rep, "URL Error for file {0} . Reason: {1}. Url: {2}".format(nom_fic, e.reason,url), general_log_filename)
       return False
  size = os.stat(rep+'/'+nom_fic).st_size
  log(rep, "File {0} downloaded with size {1} from a total size of {2}".format(nom_fic,str(size), str(total_size)), general_log_filename)
  if int(total_size) != int(size):
    log(rep, "File {0} has a different size {1} than the expected one {2}. Will not be marked as downloaded".format(nom_fic,str(size), str(total_size)), general_log_filename)
    if not db.upsertLandsatProductHistory(aoiContext.siteId, prod_name, DATABASE_DOWNLOADER_STATUS_FAILED_VALUE, prod_date, abs_prod_path, aoiContext.maxRetries):
         log(rep, "Couldn't upsert into database with status DOWNLOADING for {}".format(prod_name), general_log_filename)
         return False
    return False
  if unzipimage(prod_name, aoiContext.writeDir):
       #write the filename in history
       if not db.upsertLandsatProductHistory(aoiContext.siteId, prod_name, DATABASE_DOWNLOADER_STATUS_DOWNLOADED_VALUE, prod_date, abs_prod_path, aoiContext.maxRetries):
            log(aoiContext.writeDir, "Couldn't upsert into database with status FAILED for {}".format(prod_name), general_log_filename)
  else:
       if not db.upsertLandsatProductHistory(aoiContext.siteId, prod_name, DATABASE_DOWNLOADER_STATUS_FAILED_VALUE, prod_date, abs_prod_path, aoiContext.maxRetries):
            log(rep, "Couldn't upsert into database with status DOWNLOADING for {}".format(prod_name), general_log_filename)
            return False
  #all went well...hopefully
  return True

##################
def cycle_day(path):
    """ provides the day in cycle given the path number
    """
    cycle_day_path1  = 5
    cycle_day_increment = 7
    nb_days_after_day1=cycle_day_path1+cycle_day_increment*(path-1)

    cycle_day_path=math.fmod(nb_days_after_day1,16)
    if path>=98: #change date line
	cycle_day_path+=1
    return(cycle_day_path)



###################
def next_overpass(date1,path,sat):
    """ provides the next overpass for path after date1
    """
    date0_L5 = datetime.datetime(1985,5,4)
    date0_L7 = datetime.datetime(1999,1,11)
    date0_L8 = datetime.datetime(2013,5,1)
    if sat=='LT5':
        date0=date0_L5
    elif sat=='LE7':
        date0=date0_L7
    elif sat=='LC8':
        date0=date0_L8
    next_day=math.fmod((date1-date0).days-cycle_day(path)+1,16)
    if next_day!=0:
        date_overpass=date1+datetime.timedelta(16-next_day)
    else:
        date_overpass=date1
    return(date_overpass)

#############################"Unzip tgz file

def unzipimage(tgzfile, outputdir):
    success = False
    global general_log_filename
    if (os.path.exists(outputdir+'/'+tgzfile+'.tgz')):
        log(outputdir,  "decompressing...", general_log_filename)
        try:
            if sys.platform.startswith('linux'):
                subprocess.call('mkdir '+ outputdir+'/'+tgzfile, shell=True)   #Unix
                subprocess.call('tar zxvf '+outputdir+'/'+tgzfile+'.tgz -C '+ outputdir+'/'+tgzfile, shell=True)   #Unix
            elif sys.platform.startswith('win'):
                subprocess.call('tartool '+outputdir+'/'+tgzfile+'.tgz '+ outputdir+'/'+tgzfile, shell=True)  #W32
            success = True
            os.remove(outputdir+'/'+tgzfile+'.tgz')
            log(outputdir,  "decompress succeded. removing the .tgz file {}".format(outputdir+'/'+tgzfile), general_log_filename)
        except TypeError:
            log(outputdir, "Failed to unzip {}".format(tgzfile), general_log_filename)
            os.remove(outputdir)
    return success

#############################"Read image metadata
def read_cloudcover_in_metadata(image_path):
    output_list=[]
    fields = ['CLOUD_COVER']
    cloud_cover=0
    imagename=os.path.basename(os.path.normpath(image_path))
    metadatafile= os.path.join(image_path,imagename+'_MTL.txt')
    metadata = open(metadatafile, 'r')
    # metadata.replace('\r','')
    for line in metadata:
        line = line.replace('\r', '')
        for f in fields:
            if line.find(f)>=0:
                lineval = line[line.find('= ')+2:]
                cloud_cover=lineval.replace('\n','')
    return float(cloud_cover)

#############################"Check cloud cover limit

def check_cloud_limit(imagepath,limit):
     global general_log_path
     global general_log_filename
     removed=0
     cloudcover=read_cloudcover_in_metadata(imagepath)
     if cloudcover>limit:
          shutil.rmtree(imagepath)
          log(general_log_path, "Image was removed because the cloud cover value of {} exceeded the limit defined by the user!".format(cloudcover), general_log_filename)
          removed=1
     return removed


######################################################################################

signal.signal(signal.SIGINT, signal_handler)

def landsat_download(aoiContext):
     global g_exit_flag
     global general_log_filename

     general_log_filename = "landsat_download.log"
     general_log_path = aoiContext.writeDir
     usgsFile = aoiContext.remoteSiteCredentials

     # read password file
     try:
        f = file(usgsFile)
        (account,passwd)=f.readline().split(' ')
        if passwd.endswith('\n'):
            passwd=passwd[:-1]
        usgs={'account':account,'passwd':passwd}
        f.close()
     except :
        log(general_log_path, "Error with usgs password file", general_log_filename)
        sys.exit(-2)


     if aoiContext.proxy != None :
        try:
            f=file(aoiContext.proxy)
            (user,passwd)=f.readline().split(' ')
            if passwd.endswith('\n'):
                passwd=passwd[:-1]
            host=f.readline()
            if host.endswith('\n'):
                host=host[:-1]
            port=f.readline()
            if port.endswith('\n'):
                port=port[:-1]
            proxy={'user':user,'pass':passwd,'host':host,'port':port}
            f.close()
        except :
            log(general_log_path, "Error with proxy password file", general_log_filename)
            sys.exit(-3)

     db = LandsatAOIInfo(aoiContext.configObj.host, aoiContext.configObj.database, aoiContext.configObj.user, aoiContext.configObj.password)

     start_date = datetime.datetime(aoiContext.startSeasonYear, aoiContext.startSeasonMonth, aoiContext.startSeasonDay)
     end_date   = datetime.datetime(aoiContext.endSeasonYear, aoiContext.endSeasonMonth, aoiContext.endSeasonDay)

     for tile in aoiContext.aoiTiles:
         log(aoiContext.writeDir, "Starting the process for tile {}".format(tile), general_log_filename)
         if len(tile) != 6:
             log(aoiContext.writeDir, "The length for tile is not 6. There should be ppprrr, where ppp = path and rrr = row. The string is {}".format(tile), general_log_filename)
             continue

         product="LC8"
         remoteDir='4923'
         stations=['LGN']
         if aoiContext.landsatStation !=None:
             stations = [aoiContext.landsatStation]
         if aoiContext.landsatDirNumber !=None:
             remoteDir = aoiContext.landsatDirNumber

         path=tile[0:3]
         row=tile[3:6]
         log(aoiContext.writeDir, "path={}|row={}".format(path, row), general_log_filename)

         global downloaded_ids
         downloaded_ids=[]

         if aoiContext.proxy!=None:
             connect_earthexplorer_proxy(proxy,usgs)
         else:
             connect_earthexplorer_no_proxy(usgs)
             
         #date_asc_array = []  
         curr_date=next_overpass(start_date, int(path), product)
         #while (curr_date < end_date):
         #     date_asc_array.append(curr_date.strftime("%Y%j"))
         #     curr_date = curr_date + datetime.timedelta(16)
         #print("{}".format(date_asc_array))
         #sys.exit(0)

         while (curr_date < end_date):
             date_asc=curr_date.strftime("%Y%j")

             log(aoiContext.writeDir, "Searching for images on (julian date): {}...".format(date_asc), general_log_filename)
             curr_date=curr_date+datetime.timedelta(16)
             for station in stations:
                 for version in ['00','01','02']:
                                         if g_exit_flag:
                                             log(aoiContext.writeDir, "SIGINT was caught")
                                             sys.exit(0)
                                         nom_prod = product + tile + date_asc + station + version
                                         tgzfile = os.path.join(aoiContext.writeDir, nom_prod + '.tgz')
                                         lsdestdir = os.path.join(aoiContext.writeDir, nom_prod)
                                         url = "http://earthexplorer.usgs.gov/download/{}/{}/STANDARD/EE".format(remoteDir,nom_prod)

                                         if aoiContext.fileExists(nom_prod):
                                             #log(aoiContext.writeDir, "File {} found in history so it's already downloaded".format(nom_prod), general_log_filename))
                                             #TODO: shall this be unzipped if it does not exist?
                                             if not os.path.exists(lsdestdir):
                                                 log(aoiContext.writeDir, "Trying to decompress {}. If an error will be raised, means that the archived tgz file was phisically erased (manually or automatically) ".format(nom_prod), general_log_filename)
                                                 unzipimage(nom_prod, aoiContext.writeDir)
                                             continue
                                      
                                         # get the date by transforming it from doy to date
                                         year = date_asc[0:4]
                                         days = date_asc[4:]
                                         prod_date = (datetime.datetime(int(year), 1, 1) + datetime.timedelta(int(days))).strftime("%Y%m%dT000101")
                                         print("prod_date={}".format(prod_date))
                                         if downloadChunks(url, aoiContext.writeDir, nom_prod, prod_date, lsdestdir, aoiContext, db):
                                              downloaded_ids.append(nom_prod)                                              

         log(aoiContext.writeDir, downloaded_ids, general_log_filename)
