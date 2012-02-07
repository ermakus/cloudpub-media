Stream AVI torrent files to iPad on (ubuntu) linux
==================================================

Requirements
----------

 To convert downloaded files latest version of VLC player (available here: http://nightlies.videolan.org/) is required
 To stream video segments external server is requred (see nginx sample config).

How to run
----------

 * git clone git@github.com:ermakus/cloudpub-media.git
 * apt-get install python-tornado
 * cd cloudpub-media
 * ./server --domain=[Public IP or domain name of the WEB GUI] --port=[to listen default 8888] --files=[/Downlad/Dir]
 * Open http://[domain]:[port] on iPad and then add bookmarklet as explained on Help.

Currently only some file format is supported, the good conversion settings is welcome

