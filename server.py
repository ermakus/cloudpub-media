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

define("port", default=8888, help="run on the given port", type=int)
define('host', default="0.0.0.0", help="The binded ip host")

PER_PAGE=10

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/",      HomeHandler),
            (r"/fetch", DownloadHandler),
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            autoescape=None,
        )
        self.loader = Session()
        tornado.web.Application.__init__(self, handlers, **settings)

class BaseHandler(tornado.web.RequestHandler):
    pass

class HomeHandler(BaseHandler):
    def get(self):
        self.render("index.html", torrents=self.application.loader.torrents)

def url2name(url):
    return os.path.basename(urlsplit(url)[2])

def download(url, cookies, localFileName = None):
    localName = url2name(url)
    opener = urllib2.build_opener()
    opener.addheaders.append(('Cookie', cookies))
    r = opener.open(url)
    if r.info().has_key('Content-Disposition'):
        # If the response has Content-Disposition, we take file name from it
        localName = r.info()['Content-Disposition'].split('filename=')[1]
        if localName[0] == '"' or localName[0] == "'":
            localName = localName[1:-1]
    elif r.url != url: 
        # if we were redirected, the real file name we take from the final URL
        localName = url2name(r.url)
    if localFileName: 
        # we can force to save the file as specified name
        localName = localFileName
    f = open(localName, 'wb')
    f.write(r.read())
    f.close()
    print "Loaded", url, cookies
    return localName

class DownloadHandler(BaseHandler):

    def get(self):
        url = self.get_argument("torrent")
        cookies = self.get_argument("cookies")
        filename = download( url, cookies, "test.torrent" )
        self.application.loader.add( filename )
        self.redirect( "/" )

def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port, options.host)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()
