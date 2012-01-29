#!/usr/bin/python
from subprocess import call, Popen, PIPE
import libtorrent as lt
import time
import sys
import re

PLAYER_ADDRESS="192.168.1.2"
SERVER_ADDRESS="192.168.1.5"

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
class Stream:

    def __init__(self, torrent):
        self.info    = torrent.info
        self.handle  = torrent.handle
        self.current = 0
        self.worker  = None
        self.source  = None
        self.closed  = False
        self.onStart = EventHook()
    
    # Send piece of downloaded file to convertor pipe
    def feed(self, offset, size):
        if not self.worker:
            self.worker = Popen(['./encoder-vlc', self.path], stdin=PIPE)
        if not self.source:
            self.source = open(self.path,'r')

        self.source.seek(offset)
        data = self.source.read(size)
        self.worker.stdin.write(data)
        self.onStart.fireOnce( self )

    # Check for new pieces and feed convertor
    def pump(self):
        if self.closed:
            return
        s = self.handle.status()
        while( (self.current < self.size) and s.pieces[ self.piece ] ):
            piece_len = self.info.piece_size( self.piece )
            for fl in self.info.map_block( self.piece, 0, piece_len ):
                if fl.file_index == self.index:
                    self.feed( fl.offset, fl.size )
                    self.current += fl.size
                    self.piece   += 1
                    print >> sys.stderr, "%s: piece %d len %d\n" % (self.path, self.current, fl.size)

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

# Torrent sequental loader
class Session:

    # Constructor
    def __init__(self):
        # Create session
        self.ses = lt.session()
        self.ses.set_alert_mask(lt.alert.category_t.progress_notification)
        self.ses.listen_on(6881, 6891)
        self.torrents = []

    # Add torrent to session
    def add(self, path):
        torrent = Torrent(self, path)
        self.torrents += [torrent]
        return torrent


class Torrent:
    
    # Load torrent
    def __init__(self, session, path):
        self.path = path
        self.session  = session
        self.ses = session.ses
        self.info = lt.torrent_info(path)

        self.handle = self.ses.add_torrent({
            'ti': self.info,
            'save_path': './',
            'auto_managed': True,
            'paused': True,
            #'storage_mode':lt.storage_mode_t.storage_mode_compact
        })
        self.handle.set_sequential_download(True)

        # Construct streams from files
        self.streams = []
        num_files    = self.info.num_files()
        priority     = [0] * num_files

        for index in xrange(0,num_files):
            entry  = self.info.file_at(index)

            # Check for supported format
            if not re.match('^.+\.avi$', entry.path):
                continue

            stream = Stream(self)
            preq   = self.info.map_file(index, 0, 0)
            stream.index = index
            stream.piece = preq.piece
            stream.start = preq.start
            stream.size  = entry.size
            stream.path  = entry.path
            stream.onStart += self.stream_ready
            self.streams += [stream]
            priority[index] = 1
            print >> sys.stderr, "File %s offset %d start %s" % (stream.path, stream.piece, stream.start) 

        # Disable ignored files
        self.handle.prioritize_files( priority )

        # Increase priority of the first and last blocks
        if num_files == 1:
            # We only do this if one file is in the torrent
            priorities = [1] * self.info.num_pieces()
            priorities[0]  = 7
            priorities[-1] = 7
            self.handle.prioritize_pieces(priorities)

    # Stream ready event handler
    def stream_ready(self, stream):
        print >> sys.stderr, "Stream %s ready to play" % (stream.path) 
        try:
            call( ['/usr/bin/ssh', 'root@' + PLAYER_ADDRESS,
                    "openURL", "http://%s/%s.stream/stream.m3u8" % (SERVER_ADDRESS, stream.path) ])
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print >> sys.stderr, cmd
            print >> sys.stderr, tb
            

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
        for stream in self.streams:
            try:
                stream.pump()
            except Exception as e:
                print >> sys.stderr, "Stream error: %s" % e
                stream.close()

    # Run until complete
    def run(self):
        print >> sys.stderr, "Starting %s\n" % self.handle.name()
        self.handle.resume()

        counter = 0

        # Main cycle
        while (not self.handle.is_seed()):
            self.pump()
            self.print_status()
            counter += 1
            if not (counter % 10):
                self.print_pieces()
            time.sleep(1)
        
        self.pump()

        # close streams
        for stream in self.streams:
            stream.close()

        print >> sys.stderr, "%s complete\n" % self.handle.name()


if __name__ == '__main__':
    session = Session()
    torrent = session.add( sys.argv[1] )
    torrent.run()

