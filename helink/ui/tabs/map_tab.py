from pathlib import Path
import json

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from helink.services.map_server import get_map_server


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
        self.map=OfflineRouteMap(); root.addWidget(self.map)
    def load(self,f):
        self.map.load_route(f.data_log)


class OfflineRouteMap(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.assets = Path(__file__).resolve().parents[2] / "assets"
        self.server = get_map_server(self.assets)
        self.setPage(OfflineMapPage(self))
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.page().setBackgroundColor(Qt.white)

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

    def load_route(self, rows):
        points = [point for row in (rows or []) if (point := self._point(row))]
        payload = json.dumps({"points": points})
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
<script>
const DATA=__PAYLOAD__;
const map=L.map("map",{zoomControl:true,attributionControl:true,minZoom:7,maxZoom:12}).setView([39.65,-8.0],8);
protomapsL.leafletLayer({url:"__TILE_URL__",flavor:"light",lang:"en",attribution:"Map data from <a href=\"https://www.openstreetmap.org/copyright\" title=\"OpenStreetMap contributors ? ODbL\">OpenStreetMap contributors</a> &middot; <a href=\"https://protomaps.com\">Protomaps</a>",maxZoom:12}).addTo(map);
function popup(p){return '<div class="route-popup"><strong>Flight data</strong><br>Time: '+p.time+'<br>Altitude: '+p.altitude+' ft<br>IAS: '+p.ias+' kt<br>Heading: '+p.heading+'&deg;<br>Position: '+p.lat.toFixed(5)+', '+p.lon.toFixed(5)+'</div>';}
const pts=DATA.points||[];
if(pts.length){
 for(let i=0;i<pts.length-1;i++){L.polyline([[pts[i].lat,pts[i].lon],[pts[i+1].lat,pts[i+1].lon]],{color:"#d8292f",weight:5,opacity:.88}).bindPopup(popup(pts[i]),{maxWidth:270}).addTo(map);}
 const spacing=Math.max(1,Math.floor(pts.length/18));
 for(let i=spacing;i<pts.length-1;i+=spacing){const a=pts[i-1],b=pts[i];const angle=Math.atan2(b.lat-a.lat,b.lon-a.lon)*180/Math.PI;L.marker([b.lat,b.lon],{interactive:false,icon:L.divIcon({className:"direction-arrow",html:'<span style="display:block;transform:rotate('+(-angle)+'deg)">&#10140;</span>',iconSize:[20,20],iconAnchor:[10,10]})}).addTo(map);}
 L.circleMarker([pts[0].lat,pts[0].lon],{radius:8,color:"#fff",weight:2,fillColor:"#20a35a",fillOpacity:1}).bindPopup("<strong>Flight start</strong><br>"+popup(pts[0])).addTo(map);
 const last=pts[pts.length-1];L.circleMarker([last.lat,last.lon],{radius:8,color:"#fff",weight:2,fillColor:"#d8292f",fillOpacity:1}).bindPopup("<strong>Flight end</strong><br>"+popup(last)).addTo(map);
 map.fitBounds(
  L.latLngBounds(pts.map(function(p){return[p.lat,p.lon]})).pad(.12),
  {padding:[28,28],maxZoom:12}
 );
 if(map.getZoom()<7){map.setZoom(7);}
}else{const message=document.createElement("div");message.className="empty";message.textContent="No valid route coordinates were found for this flight.";document.body.appendChild(message);}
</script></body></html>"""
        html = html.replace("__PAYLOAD__", payload).replace("__TILE_URL__", tile_url)
        self.setHtml(html, QUrl(self.server.base_url))
