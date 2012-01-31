#!/usr/bin/env python
import os.path
import re
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import unicodedata
import sys
import urllib2
from urlparse import urlsplit
from tornado.options import define, options
from tornado.escape import url_escape
from loader import Session, Torrent
import settings

define("port", default=8888, help="run on the given port", type=int)
define('host', default="0.0.0.0", help="The binded ip host")

PER_PAGE=10

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/",      HomeHandler),
            (r"/fetch", DownloadHandler),
            (r"/ctrl",  ControlHandler),
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
        )
        self.loader = Session()
        self.loader.load()
        tornado.web.Application.__init__(self, handlers, **settings)

class BaseHandler(tornado.web.RequestHandler):
    pass

class HomeHandler(BaseHandler):
    def get(self):
        self.render("index.html",
                torrents=self.application.loader.torrents,
                SERVER_ADDRESS=settings.SERVER_ADDRESS)

def url2name(url):
    return os.path.basename(urlsplit(url)[2])

def download(url, referer, cookies):
    opener = urllib2.build_opener()
    opener.addheaders.append(('Referer', referer))
    opener.addheaders.append(('Cookie', cookies))
    r = opener.open(url)
    localName = url2name(url)
    if r.info().has_key('Content-Disposition'):
        # If the response has Content-Disposition, we take file name from it
        localName = r.info()['Content-Disposition'].split('filename=')[1]
    elif r.url != url: 
        # if we were redirected, the real file name we take from the final URL
        localName = url2name(r.url)
    localName = settings.DOWNLOAD_DIR + "/" + localName.strip("\"';")
    f = open( localName, 'wb')
    f.write(r.read())
    f.close()
    return localName

class DownloadHandler(BaseHandler):

    def get(self):
        url = self.get_argument("torrent")
        cookies = self.get_argument("cookies")
        referer = self.get_argument("ref")
        filename = download( url, referer, cookies )
        self.application.loader.add( filename )
        self.application.loader.save()
        self.redirect( "/" )

class ControlHandler(BaseHandler):

    def get(self):
        torrent = self.get_argument("torrent")
        filename = self.get_argument("file")
        command = self.get_argument("command","start")
        torrent = self.application.loader[torrent]
        if command == "start":
            torrent.select( [filename] )    
            torrent.start()
        else:
            torrent.stop()
        self.redirect( "/" )

def main():
    tornado.options.parse_command_line()
    app = Application()
    http_server = tornado.httpserver.HTTPServer( app )
    http_server.listen(options.port, options.host)
    try:
        tornado.ioloop.IOLoop.instance().start()
    finally:
        app.loader.stop()

if __name__ == "__main__":
    main()
