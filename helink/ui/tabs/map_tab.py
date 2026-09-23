from pathlib import Path
import json
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from helink.services.map_server import get_map_server
from helink.services.airport_formatter import format_airport


class OfflineMapPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if (
            navigation_type == QWebEnginePage.NavigationTypeLinkClicked
            and url.scheme() in ('http', 'https')
            and url.host() not in ('127.0.0.1', 'localhost')
        ):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(
            url, navigation_type, is_main_frame
        )


class MapTab(QWidget):
    def __init__(self):
        super().__init__()
        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setContentsMargins(16, 12, 16, 12)
        self.status.hide()
        root.addWidget(self.status)
        self.map=OfflineRouteMap(); root.addWidget(self.map, 1)
        self.map.status_changed.connect(self._show_status)

    def _show_status(self, message):
        self.status.setText(message)
        self.status.setVisible(bool(message))

    def load(self,f):
        self.map.load_route(
            f.data_log,
            format_airport(f.destination) if f.destination else '',
        )


class OfflineRouteMap(QWebEngineView):
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.assets = Path(__file__).resolve().parents[2] / "assets" / "map"
        self.server = get_map_server(self.assets)
        self.setPage(OfflineMapPage(self))
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.page().setBackgroundColor(Qt.white)
        self._document_name = f'route-{uuid.uuid4().hex}.html'
        self.loadFinished.connect(self._load_finished)
        self.renderProcessTerminated.connect(
            lambda *_: self.status_changed.emit(
                'The map renderer stopped. Reopen the flight to reload the map.'
            )
        )
        server, name = self.server, self._document_name
        self.destroyed.connect(lambda *_: server.remove_document(name))

    def _load_finished(self, ok):
        self.status_changed.emit(
            '' if ok else
            'The offline map could not be loaded. Reopen the flight to try again.'
        )
        if ok and self.isVisible():
            self._refresh_map()

    def _refresh_map(self):
        self.page().runJavaScript(
            'if (window.refreshRouteMap) window.refreshRouteMap(true);'
        )

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._refresh_map)

    @staticmethod
    def _point(row):
        try:
            lat = float(row.latitude)
            lon = float(row.longitude)
        except (TypeError, ValueError):
            return None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        if not (-11 <= lon <= 5 and 35 <= lat <= 45):
            return None

        def value(attribute):
            item = getattr(row, attribute)
            return str(item).strip() if item is not None and str(item).strip() else "-"

        return {
            "lat": lat,
            "lon": lon,
            "time": value("timestamp"),
            "altitude": value("alt_ind"),
            "ias": value("ias"),
            "heading": value("heading"),
        }

    def load_route(self, rows, destination=''):
        points = [point for row in (rows or []) if (point := self._point(row))]
        self.status_changed.emit('Loading offline map...')
        # Keep flight data in memory and escape script delimiters in CSV values.
        payload = json.dumps({"points": points, "destination": destination}).replace('<', '\\u003c')
        tile_url = self.server.base_url + "portugal_z12.pmtiles"
        html = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="leaflet.css">
<style>
html,body,#map{height:100%;width:100%;margin:0;background:#edf2f7}body{font-family:Inter,Segoe UI,Arial,sans-serif}
.leaflet-container{background:#edf2f7}.leaflet-control-attribution{font-size:10px}
.route-popup{min-width:185px;color:#172033;line-height:1.55}.route-popup strong{color:#0b1d3a}
.empty{position:absolute;z-index:1000;inset:20px auto auto 50%;transform:translateX(-50%);background:#fff;border:1px solid #ccd6e4;border-radius:10px;padding:10px 16px;color:#45556d;box-shadow:0 5px 18px rgba(15,31,54,.14)}
.direction-arrow{color:#1558d6;font-size:18px;font-weight:800;text-shadow:0 1px 2px #fff}
</style></head><body><div id="map"></div>
<script src="leaflet.js"></script><script src="protomaps-leaflet.js"></script>
<div id="map-status" class="empty">Loading offline map...</div>
<script>
const statusMessage=document.getElementById("map-status");
function showMapError(message){statusMessage.hidden=false;statusMessage.textContent=message;}
try {
if(typeof L==="undefined" || typeof protomapsL==="undefined"){
 throw new Error("Offline map components are missing. Check the application installation.");
}
const DATA=__PAYLOAD__;
const map=L.map("map",{zoomControl:true,attributionControl:true,preferCanvas:true,minZoom:7,maxZoom:12}).setView([39.65,-8.0],8);
protomapsL.leafletLayer({url:"__TILE_URL__",flavor:"light",lang:"en",attribution:"Map data from <a href=\"https://www.openstreetmap.org/copyright\" title=\"OpenStreetMap contributors ? ODbL\">OpenStreetMap contributors</a> &middot; <a href=\"https://protomaps.com\">Protomaps</a>",maxZoom:12}).addTo(map);
function escapeText(value){const element=document.createElement("span");element.textContent=String(value);return element.innerHTML;}
function popup(p){return '<div class="route-popup"><strong>Flight data</strong><br>Time: '+escapeText(p.time)+'<br>Altitude: '+escapeText(p.altitude)+' ft<br>IAS: '+escapeText(p.ias)+' kt<br>Heading: '+escapeText(p.heading)+'&deg;<br>Position: '+p.lat.toFixed(5)+', '+p.lon.toFixed(5)+'</div>';}
const pts=DATA.points||[];
const routeBounds=pts.length?L.latLngBounds(pts.map(p=>[p.lat,p.lon])):null;
window.refreshRouteMap=function(fit){
 map.invalidateSize({pan:false});
 if(fit && routeBounds){map.fitBounds(routeBounds.pad(.12),{padding:[28,28],maxZoom:12,animate:false});}
};
new ResizeObserver(()=>window.refreshRouteMap(false)).observe(document.getElementById("map"));
statusMessage.hidden=true;
if(pts.length){
 const route=L.polyline(pts.map(p=>[p.lat,p.lon]),{color:"#d8292f",weight:5,opacity:.88}).addTo(map);
 route.on("click",function(event){
  const clicked=map.latLngToLayerPoint(event.latlng);
  let nearest=pts[0],distance=Infinity;
  for(const point of pts){
   const projected=map.latLngToLayerPoint([point.lat,point.lon]);
   const squared=(projected.x-clicked.x)**2+(projected.y-clicked.y)**2;
   if(squared<distance){distance=squared;nearest=point;}
  }
  L.popup({maxWidth:270}).setLatLng([nearest.lat,nearest.lon]).setContent(popup(nearest)).openOn(map);
 });
 const spacing=Math.max(1,Math.floor(pts.length/18));
 for(let i=spacing;i<pts.length-1;i+=spacing){const a=pts[i-1],b=pts[i];const angle=Math.atan2(b.lat-a.lat,b.lon-a.lon)*180/Math.PI;L.marker([b.lat,b.lon],{interactive:false,icon:L.divIcon({className:"direction-arrow",html:'<span style="display:block;transform:rotate('+(-angle)+'deg)">&#10140;</span>',iconSize:[20,20],iconAnchor:[10,10]})}).addTo(map);}
 L.circleMarker([pts[0].lat,pts[0].lon],{radius:8,color:"#fff",weight:2,fillColor:"#20a35a",fillOpacity:1}).bindPopup("<strong>Flight start</strong><br>"+popup(pts[0])).addTo(map);
 const last=pts[pts.length-1];const destination=DATA.destination?'<br><strong>Destination:</strong> '+escapeText(DATA.destination):'';L.circleMarker([last.lat,last.lon],{radius:8,color:"#fff",weight:2,fillColor:"#d8292f",fillOpacity:1}).bindPopup("<strong>Flight end</strong>"+destination+"<br>"+popup(last)).addTo(map);
 map.fitBounds(
  L.latLngBounds(pts.map(function(p){return[p.lat,p.lon]})).pad(.12),
  {padding:[28,28],maxZoom:12}
 );
 if(map.getZoom()<7){map.setZoom(7);}
}else{showMapError("No valid route coordinates were found for this flight.");}
} catch(error) {
 showMapError(error.message || "The offline map could not be displayed.");
 console.error(error);
}
</script></body></html>"""
        html = html.replace("__PAYLOAD__", payload).replace("__TILE_URL__", tile_url)
        url = self.server.set_document(self._document_name, html)
        # Normal loopback HTTP navigation supports HTML larger than 2 MB.
        self.setUrl(QUrl(url + '?load=' + uuid.uuid4().hex))
