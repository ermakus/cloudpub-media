(function(){
	var serverAddress = 'http://{{ SERVER_ADDRESS }}/';
	var a=document.getElementsByTagName('a');
	
	for(var i=0,j=a.length;i<j;i++){
		
		// a[i].getAttribute('href') will return a relative path
		var linkurl = a[i].href;
		
		// limit link changes to following matches
		
		// search for terms after last '/' ie. the file name : (.torrent)
		var testUrl = linkurl.substring(linkurl.lastIndexOf('/') + 1, linkurl.length);
		var testResult = testUrl.search(/(\.torrent$)/i);
		// search for terms anywhere in url : (magnet link) (directories starting with: /get | /download | /dl)
		if (testResult == -1){
			var testResult = linkurl.search(/(magnet:\?|\/get|\/download|\/dl|\/torrent)/i);
		}
		
		if (testResult != -1){
			var img=document.createElement('img');
			img.setAttribute('src', serverAddress + 'static/l.png' );
			img.setAttribute('style','width:32px!important;height:32px!important;border:none!important;');
            img.onclick = (function(url) {
                return function() {
			        window.open(serverAddress + 
                            'fetch?torrent=' + encodeURIComponent(url) + 
                            '&cookies=' + encodeURIComponent(document.cookie) +
                            '&ref=' + encodeURIComponent(document.location.href));
                    return false;
                }
            })(linkurl);
    		a[i].appendChild(img);
		}
	}
})();
