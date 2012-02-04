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
from validator import ValidationMixin
import settings

define("port", default=8888, help="run on the given port", type=int)
define('host', default="0.0.0.0", help="The binded ip host")

PER_PAGE=10

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/",         HomeHandler),
            (r"/login",    LoginHandler),
            (r"/logout",   LogoutHandler),
            (r"/register", RegisterHandler),
            (r"/fetch",    DownloadHandler),
            (r"/ctrl",     ControlHandler),
            (r"/del",      DeleteHandler),
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            cookie_secret='LHD(*#EHKJDFBSD(*F#RGM>NJK',
        )
        self.loader = Session()
        self.loader.load()
        tornado.web.Application.__init__(self, handlers, **settings)

class BaseHandler(tornado.web.RequestHandler, ValidationMixin):

    def get_login_url(self):
        return u"/login"

    def get_current_user(self):
        # If password is not set return default user
        if settings.AUTH_PASSWORD == "":
            return settings.AUTH_USER
        # .. else deserialize from session
        user_json = self.get_secure_cookie("user")
        if user_json:
            return tornado.escape.json_decode(user_json)
        else:
            return None

    def set_current_user(self, user):
        if user:
            self.set_secure_cookie("user", tornado.escape.json_encode(user))
        else:
            self.clear_cookie("user")

class LoginHandler(BaseHandler):

    def get(self):
        self.render("login.html", next=self.get_argument("next","/"), errors={}, username="")

    def isValid(self, password):
        return password == settings.AUTH_PASSWORD

    def post(self):
        username = self.valid("username", ValidationMixin.EMAIL)
        password = self.valid("password", self.isValid)

        if len(self.errors) > 0:
            self.render("login.html", next=self.get_argument("next","/"), errors=self.errors, username=username)

        self.set_current_user(username)
        self.redirect(self.get_argument("next", u"/"))


class RegisterHandler(BaseHandler):

    def post(self):
        username = self.valid("username", ValidationMixin.EMAIL)
        password = self.valid("password")

        if len(self.errors) > 0:
            self.render("login.html", next=self.get_argument("next","/"), errors=self.errors, username=username)

        self.set_current_user(username)
        self.redirect(self.get_argument("next", u"/"))

class LogoutHandler(BaseHandler):

    def get(self):
        self.clear_cookie("user")
        self.redirect( self.get_login_url() )


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
            torrent.select( self.request.arguments['file'] )
            torrent.start()
        else:
            torrent.stop()
        self.redirect( "/" )

class DeleteHandler(BaseHandler):

    def get(self):
        torrent = self.get_argument("torrent")
        torrent = self.application.loader[torrent]
        torrent.stop()
        torrent.delete()
        self.application.loader.save()
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
