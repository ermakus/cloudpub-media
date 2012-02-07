#!/usr/bin/python
from __future__ import division
from subprocess import call, Popen, PIPE
import libtorrent as lt
import time
import sys
import re
import threading
import ConfigParser
import os
import shutil
import jsonpickle
import settings

# Event pattern
class EventHook(object):

    def __init__(self):
        self.__handlers = []
        self.count = 0

    def __iadd__(self, handler):
        self.__handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.__handlers.remove(handler)
        return self

    def fire(self, *args, **keywargs):
        for handler in self.__handlers:
            handler(*args, **keywargs)

    def fireOnce(self, *args, **keywargs):
        if self.count:
            return
        self.count += 1
        for handler in self.__handlers:
            handler(*args, **keywargs)


    def clearObjectHandlers(self, inObject):
        self.count = 0
        for theHandler in self.__handlers:
            if theHandler.im_self == inObject:
                self -= theHandler


# Incapsulate decoding stream
class Stream(object):

    def __init__(self, torrent):
        self.torrent = torrent
        # True if stream is selected for download
        self.selected = False
        # converted piece
        self.downloaded = 0
        # Index of first piece in all image
        self.piece = 0
        # Number of converted bytes
        self.converted = 0
        # Convertor process handle
        self.worker  = None
        # Source file handle
        self.source  = None
        # Stream closed flag
        self.closed  = False
        # Complete flag
        self.complete = False
        # On conversion started hook
        self.onStart = EventHook()


    # True if decoded data is available
    def isAvailable(self):
        try:
            open(self.path + ".stream/stream.m3u8")
        except IOError as e:
            return False
        return True

    def getFilename(self):
        return self.path[len(settings.DOWNLOAD_DIR)+1:]

    def isComplete(self):
        return self.closed

    def getDownloaded(self):
        s = self.torrent.info
        pieces = self.torrent.handle.status().pieces
        downloaded = 0
        for index in xrange( self.piece, self.piece + min( int(self.size / s.piece_length()), len(pieces) )):
            if pieces[ index ]:
                downloaded+=1
        return round((downloaded * s.piece_length() / self.size) * 100.0)

    def getConverted(self):
        s = self.torrent.info
        return round((self.converted * s.piece_length() / self.size) * 100.0)

    # Send piece of downloaded file to convertor pipe
    def feed(self, offset, size):
        if not self.worker:
            self.worker = Popen([ settings.BASE_DIR + '/encoder-' + settings.ENCODER, self.path], stdin=PIPE, cwd=settings.DOWNLOAD_DIR)
        if not self.source:
            self.source = open( self.path,'r')
            self.closed = False

        self.source.seek(offset)
        data = self.source.read(size)
        self.worker.stdin.write(data)
        self.onStart.fireOnce( self )

    # Check for new pieces and feed convertor
    def pump(self):
        # Ignore closed or unselected streams
        if self.closed or not self.selected:
            return
        # Get torent status
        s = self.torrent.handle.status()
        # Step over all available pieces from last converted
        piece_len = self.torrent.info.piece_length()
        piece = self.piece + self.converted
        piece_size = self.torrent.info.piece_size( piece  )
        size = int(self.size / piece_len)
        if( (self.converted < size) and s.pieces[ piece ] ):
            # Break if thread stopped
            if self.torrent.quit:
                return
            # Map piece to files
            for fl in self.torrent.info.map_block( piece, 0, piece_len ):
                # Only handle file of this stream
                if fl.file_index == self.index:
                    # Feed block to convertor
                    self.converted += 1
                    piece += 1
                    print >> sys.stderr, "%s: piece %d len %d\n" % (self.path, fl.offset, fl.size)
                    self.feed( fl.offset, fl.size )

    # Close opened handles
    def close(self):
        if self.worker:
            try:
                self.worker.stdin.close()
            except:
                pass
            self.worker = None
        if self.source:
            try:
                self.source.close()
            except:
                pass
            self.source = None
        self.closed = True

    def delete(self):
        try:
            os.remove( self.path )
        except OSError as e:
            print >> sys.stderr, "Stream file %s not found" % (self.path) 
        try:
            shutil.rmtree( self.path + ".stream" )
        except OSError as e:
            print >> sys.stderr, "Stream folder %s.stream not found" % (self.path) 

# Torrent sequental loader
class Session(object):

    # Constructor
    def __init__(self):
        # Create session
        self.torrents = []
        self.count = 0
        self.rebind()

    def rebind(self):
        self.ses = lt.session()
        self.ses.set_alert_mask(lt.alert.category_t.progress_notification)
        self.ses.listen_on(6881, 6891)
        for torrent in self.torrents:
            torrent.session = self
            torrent.rebind()

    # Add torrent to session
    def add(self, path):
        torrent = Torrent(self, path)
        torrent.index = self.count
        self.count += 1
        self.torrents.append(torrent)
        return torrent

    # Get torrent by filename
    def __getitem__(self, path):
        for t in self.torrents:
            if t.path == path:
                return t
        return None

    # Stop all torrents
    def stop(self):
        for torrent in self.torrents:
            torrent.stop()

    # Save session
    def save(self):
        state = jsonpickle.encode(self)
        with open( settings.DOWNLOAD_DIR + '/state.json', 'wb') as config:
            config.write(state)

    # Load session
    @staticmethod
    def load():
        config = ConfigParser.ConfigParser()
        try:
            with open( settings.DOWNLOAD_DIR + '/state.json' ,'rb') as config:
                state = config.read()
                clone = jsonpickle.decode(state)
                clone.rebind()
                return clone
        except Exception as e:
            print >> sys.stderr, "Load error, reset session: %s" % e
            return Session()


class TorrentThread(threading.Thread):

    def __init__(self, torrent):
        threading.Thread.__init__(self)
        self.torrent = torrent

    def run(self):
        self.torrent.run()

# Torrent wrapper
class Torrent(object):
    
    # Load torrent
    def __init__(self, session, path):
        self.started = False
        self.quit = False
        self.path = path
        self.complete = False
        self.session  = session
        self.thread = None
        self.streams = []
        self.rebind()

    def rebind(self):
        self.info = lt.torrent_info(self.path)
        print >> sys.stderr, "Rebind torrent: %s" % (self.path) 
        self.handle = self.session.ses.add_torrent({
            'ti': self.info,
            'save_path': './',
            'auto_managed': True,
            'paused': True,
            'save_path': str(settings.DOWNLOAD_DIR)
        })
        self.handle.set_sequential_download(True)
        self.handle.pause()

        # Construct streams from files
        num_files    = self.info.num_files()

        for index in xrange(0,num_files):
            entry  = self.info.file_at(index)

            # Check for supported format
            if not re.match('^.+\.(avi|mkv|ogg|mp4|wmv|mov|vob|3gp|flv)$', entry.path):
                continue

            preq   = self.info.map_file(index, 0, 0)
            path   = settings.DOWNLOAD_DIR + "/" + entry.path
            stream = self[ path ]
            if not stream:
                stream = Stream(self)
                stream.index = index
                stream.selected = True
                stream.path  = path
                self.streams.append(stream)
            stream.torrent = self
            stream.piece = preq.piece
            stream.start = preq.start
            stream.size  = entry.size
            stream.onStart = EventHook()
            stream.onStart += self.stream_ready


    def getFilename(self):
        return os.path.basename( self.path )

    def delete(self):
        for stream in self.streams:
            stream.delete()
        try:
            os.remove( self.path )
        except OSError as e:
            print >> sys.stderr, "File %s not found" % (self.path) 
        finally:
            self.session.ses.remove_torrent( self.handle, lt.options_t.delete_files )
            self.session.torrents.remove(self)
    # Return stream by path
    def __getitem__(self, path):
        for s in self.streams:
            if s.path == path:
                return s
        return None

    # Stream ready event handler
    def stream_ready(self, stream):
        print >> sys.stderr, "Stream %s ready to play" % (stream.path) 
        # Here we can open URL on remote device
        if not settings.PLAYER_ADDRESS:
            return
        try:
            call( ['/usr/bin/ssh', 'root@' + settings.PLAYER_ADDRESS,
                    "openURL", "http://%s/%s.stream/stream.m3u8" % (settings.SERVER_ADDRESS, stream.path) ])
        except Exception as e:
            print >> sys.stderr, cmd

    # Print status line
    def print_status(self):
       s = self.handle.status()
       state_str = ['queued', 'checking', 'downloading metadata', \
          'downloading', 'finished', 'seeding', 'allocating', 'checking fastresume']
       print >> sys.stderr, "\r%.2f%% complete (down: %.1f kb/s up: %.1f kB/s peers: %d) %s" % \
          (s.progress * 100, s.download_rate / 1000, s.upload_rate / 1000, \
          s.num_peers, state_str[s.state]),
       sys.stderr.flush()

    # Print downloaded pieces
    def print_pieces(self):
        s = self.handle.status()
        print >> sys.stderr, "\n", ''.join(["X" if s.pieces[index] else '-' for index in xrange(0, self.info.num_pieces())])

    # Pump data to convertors
    def pump(self):
        done = True
        for stream in self.streams:
            try:
                stream.pump()
                if not stream.isComplete():
                    done = False
            except Exception as e:
                print >> sys.stderr, "Stream error: %s" % e
                stream.close()
        self.complete = done
        return self.complete

    def select(self, streams):
        for stream in self.streams:
            stream.selected = (stream.path in streams)
        self.prepare()

    # Prepare selected streams for download
    def prepare(self):
        num_files = self.info.num_files()
        # Unselect all files
        priorities = [0] * num_files
        # Select only marked streams
        for stream in self.streams:
            stream.closed = False
            if stream.selected:
                priorities[stream.index] = 1
        self.handle.prioritize_files(priorities)

        # If this is single file torrent
        if num_files == 1:
            # ... then increase priority of the first and last blocks
            priorities = [1] * self.info.num_pieces()
            priorities[0]  = 7
            priorities[-1] = 7
            self.handle.prioritize_pieces(priorities)
 
    # Run until complete
    def run(self):
        print >> sys.stderr, "Starting %s\n" % self.handle.name()


        self.handle.resume()
        self.started = True

        counter = 0

        done = False
        # Main cycle
        while (not done and not self.quit):
            done = self.pump()
            self.print_status()
            counter += 1
            if not (counter % 10):
                self.print_pieces()
            time.sleep(1)
        
        self.pump()
        self.handle.pause()

        # close streams
        for stream in self.streams:
            stream.close()

        self.started = False
        self.quit = False
        print >> sys.stderr, "%s complete\n" % self.handle.name()

    def start(self):
        if not self.thread:
            self.thread = TorrentThread( self )
            self.thread.start()

    def stop(self):
        if self.thread and self.thread.isAlive():
            self.quit = True
            self.thread.join()
        self.thread = None

if __name__ == '__main__':
    session = Session()
    torrent = session.add( sys.argv[1] )
    torrent.run()

