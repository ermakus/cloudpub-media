(function(){
	var serverAddress = "192.168.1.5:8888";
	var a=document.getElementsByTagName('a');
	
	for(var i=0,j=a.length;i<j;i++){
		
		// a[i].getAttribute('href') will return a relative path
		var linkurl = a[i].href;
		
		// limit link changes to following matches
		
		// search for terms after last "/" ie. the file name : (.torrent)
		var testUrl = linkurl.substring(linkurl.lastIndexOf('/') + 1, linkurl.length);
		var testResult = testUrl.search(/(\.torrent$)/i);
		// search for terms anywhere in url : (magnet link) (directories starting with: /get | /download | /dl)
		if (testResult == -1){
			var testResult = linkurl.search(/(magnet:\?|\/get|\/download|\/dl|\/torrent)/i);
		}
		
		if (testResult != -1){
			var img=document.createElement('img');
		    img.setAttribute('class', 'new-window');
			img.setAttribute('src','data:image/gif;base64,'+
                            'R0lGODlhEAAMALMLAL66tBISEjExMdTQyBoaGjs7OyUlJWZmZgAAAMzMzP///////wAAAAAAAAAAAAAA'+
                            'ACH5BAEAAAsALAAAAAAQAAwAAAQ/cMlZqr2Tps13yVJBjOT4gYairqohCTDMsu4iHHgwr7UA/LqdopZS'+
                            'DBBIpGG5lBQH0GgtU9xNJ9XZ1cnsNicRADs=');
			img.setAttribute('style','width:16px!important;height:12px!important;border:none!important;');
            img.onclick = (function(url) {
                return function() {
			        window.open("http://" + serverAddress + 
                            "/fetch?torrent=" + encodeURIComponent(url) + 
                            "&cookies=" + encodeURIComponent(document.cookie));
                    return false;
                }
            })(linkurl);
    		a[i].appendChild(img);
		}
	}
})();
