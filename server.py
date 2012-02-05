#!/usr/bin/env python
import os.path
import re
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.auth
import unicodedata
import sys
import urllib2
from urlparse import urlsplit
from tornado.options import define, options
from tornado.escape import url_escape

from loader import Session, Torrent
from validator import ValidationMixin
import settings

define("port",   default=8888, help="run on the given port", type=int)
define('host',   default="0.0.0.0", help="The binded ip host")
define('domain', default="localhost", help="Public domain")

PER_PAGE=10

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/",         HomeHandler),
            (r"/auth",     AuthHandler),
            (r"/logout",   LogoutHandler),
            (r"/fetch",    DownloadHandler),
            (r"/ctrl",     ControlHandler),
            (r"/del",      DeleteHandler),
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            cookie_secret='LHD(*#EHKJDFBSD(*F#RGM>NJK',
        )
        self.loader = Session.load()
        tornado.web.Application.__init__(self, handlers, **settings)

class BaseHandler(tornado.web.RequestHandler, ValidationMixin):

    def get_login_url(self):
        return u"/login"

    def get_error_html(self, status_code, message):
        return "<body class='error'>%s (%d)</body>" % (message, status_code)

    def send_error(self, status_code=500, **kwargs):
        """Sends the given HTTP error code to the browser.

        We also send the error HTML for the given error code as returned by
        get_error_html. Override that method if you want custom error pages
        for your application.
        """
        if self._headers_written:
            logging.error("Cannot send error response after headers written")
            if not self._finished:
                self.finish()
            return
        self.clear()
        self.set_status(status_code)
        message = self.get_error_html(status_code, **kwargs)
        self.finish(message)

    # Hook that handeld request exceptions and
    # send 500 Exception Message to client
    def _handle_request_exception(self, e): 
        self.send_error( 500, e )

    # Return current session context
    # Shoud load it locally or from storage
    def get_current_user(self):
        user_json = self.get_secure_cookie("user")
        if user_json:
            return tornado.escape.json_decode(user_json)
        else:
            return None

    # Set and save session locally and 
    def set_current_user(self, user):
        if user:
            self.set_secure_cookie("user", tornado.escape.json_encode(user))
        else:
            self.clear_cookie("user")

class LogoutHandler(BaseHandler):

    def get(self):
        self.redirect("/")
        self.clear_cookie("user")

class AuthHandler(BaseHandler, tornado.auth.GoogleMixin):

    @tornado.web.asynchronous
    def get(self):
        if self.get_argument("openid.mode", None):
            self.get_authenticated_user(self.async_callback(self._on_auth))
        else:
            self.authenticate_redirect()

    def _on_auth(self, user):
        if not user:
            raise tornado.web.HTTPError(500, "Google auth failed")
        print sys.stderr, "Authenticated", user
        self.set_secure_cookie("user", tornado.escape.json_encode(user))
        self.redirect("/")

class HomeHandler(BaseHandler):
    def get(self):
        user = self.get_current_user()
        if not user:
            self.redirect("/auth")
        else:
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
        if not torrent:
            self.redirect( "/" )

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
    settings.SERVER_ADDRESS = options.domain
    http_server.listen(options.port, options.host)
    try:
        tornado.ioloop.IOLoop.instance().start()
    finally:
        app.loader.stop()

if __name__ == "__main__":
    main()
