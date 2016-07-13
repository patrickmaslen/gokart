var stylecache = {};
var text_style = new ol.style.Text({
    offsetX: 12,
    textAlign: "left",
    font: "12px Helvetica,Roboto,Arial,sans-serif",
    stroke: new ol.style.Stroke({
        color: "#fff",
        width: 4
    })
});
var initStyle = function(icon) {
    var imageicon = new ol.style.Icon({
        src: gokart.svgToPNG(icon),
        opacity: .9
    });
    var style = new ol.style.Style({
        image: imageicon,
        text: text_style
    });
    stylecache[icon] = style
    return style;
};
Vue.partial("resourceInfo", document.querySelectorAll("#resourceInfo")[0].innerHTML);
var addResource = function(f) {
    var color = "_red";
    if (f.get("age") < 24) {
        color = "_orange"
    };
    if (f.get("age") < 3) {
        color = "_yellow"
    };
    if (f.get("age") <= 1) {
        color = "_green"
    };
    f.set("icon", "static/symbols/device/" + f.get("symbolid") + color + ".svg");
    f.set("label", f.get("name") || f.get("callsign") || f.get("rego") || f.get("deviceid"));
    f.set("time", moment(f.get("seen")).toLocaleString());
    // Set a different vue template for rendering
    f.set("partialId", "resourceInfo");
    // Set id for select tools
    f.set("selectId", f.get("deviceid"));
}
var resource_tracking_style = function(f, res) {
    var style = stylecache[f.get('icon')] || initStyle(f.get('icon'))
    if (gokart.pngs[style.getImage().iconImage_.src_]) {
        var style = initStyle(f.get('icon'))
    };
    if (res < 0.002) {
        style.getText().setText(f.get("label"));
    } else {
        style.getText().setText("");
    }
    return style
}

// pack-in catalogue
var catalogue = [{
    init: gokart.createWFSLayer,
    name: "Resource Tracking",
    id: 'dpaw:resource_tracking',
    style: resource_tracking_style,
    onadd: addResource,
    refresh: 30
}, {
    init: gokart.createWFSLayer,
    name: "Resource Tracking History",
    id: 'dpaw:tracking_history_view',
    style: resource_tracking_style,
    onadd: addResource,
    cql_filter: false
}, {
    init: gokart.createTileLayer,
    name: "Firewatch Hotspots 72hrs",
    id: "landgate:firewatch_ecu_hotspots_last_0_72",
    format: "image/png",
    refresh: 60
}, {
    init: gokart.createTimelineLayer,
    name: "Himawari-8 Hotspots",
    id: "himawari8:hotspots",
    source: "/hi8/AHI_TKY_FHS",
    params: {
        FORMAT: "image/png"
    },
    refresh: 300,
}, {
    init: gokart.createTimelineLayer,
    name: "Himawari-8 True Colour",
    id: "himawari8:bandtc",
    source: "/hi8/AHI_TKY_b321",
    refresh: 300,
    base: true
}, {
    init: gokart.createTimelineLayer,
    name: "Himawari-8 Band 3",
    id: "himawari8:band3",
    source: "/hi8/AHI_TKY_b3",
    refresh: 300,
    base: true
}, {
    init: gokart.createTimelineLayer,
    name: "Himawari-8 Band 7",
    id: "himawari8:band7",
    source: "/hi8/AHI_TKY_b7",
    refresh: 300,
    base: true
}, {
    init: gokart.createTimelineLayer,
    name: "Himawari-8 Band 15",
    id: "himawari8:band15",
    source: "/hi8/AHI_TKY_b15",
    refresh: 300,
    base: true
}, {
    init: gokart.createTileLayer,
    name: "State Map Base",
    id: 'cddp:smb_250K',
    base: true
}, {
    init: gokart.createTileLayer,
    name: "Virtual Mosaic",
    id: 'landgate:LGATE-V001',
    base: true
}];


// load map with default layers
gokart.init(catalogue, ['dpaw:resource_tracking', 'cddp:smb_250K'])
gokart.loadRemoteCatalogue('https://oim.dpaw.wa.gov.au/catalogue/api/records?format=json&application__name=sss');

var historyLayer = gokart.getLayer("dpaw:tracking_history_view");
var trackingLayer = gokart.getLayer("dpaw:resource_tracking");

// load custom annotation tools
var hotSpotStyle = new ol.style.Style({
    image: new ol.style.Circle({
        fill: new ol.style.Fill({
            color: "#b43232"
        }),
        radius: 8
    })
});

var hotSpotDraw = new ol.interaction.Draw({
    type: "Point",
    features: gokart.ui.features,
    style: hotSpotStyle
});

var spotFireStyle = new ol.style.Style({
    image: new ol.style.Icon({
        anchor: [0.5, 0.5],
        anchorXUnits: "fraction",
        anchorYUnits: "fraction",
        src: "static/symbols/svgs/sss/spotfire.svg"
    })
});

var spotFireDraw = new ol.interaction.Draw({
    type: "Point",
    features: gokart.ui.features,
    style: spotFireStyle
});


var divisionStyle = new ol.style.Style({
    image: new ol.style.Icon({
        anchor: [0.5, 0.5],
        anchorXUnits: "fraction",
        anchorYUnits: "fraction",
        src: "static/symbols/svgs/sss/division.svg"
    })
});

var divisionDraw = new ol.interaction.Draw({
    type: "Point",
    features: gokart.ui.features,
    style: divisionStyle
});


var sectorStyle = new ol.style.Style({
    image: new ol.style.Icon({
        anchor: [0.5, 0.5],
        anchorXUnits: "fraction",
        anchorYUnits: "fraction",
        src: "static/symbols/svgs/sss/sector.svg"
    })
});

var sectorDraw = new ol.interaction.Draw({
    type: "Point",
    features: gokart.ui.features,
    style: sectorStyle
});


var fireLineStyle = new ol.style.Style({
    stroke: new ol.style.Stroke({
        width: 8.0,
        lineDash: [20, 20],
        color: [0, 114, 0, 1.0],
        lineCap: "square",
        lineJoin: "bevel"
    })
});

var fireLineDraw = new ol.interaction.Draw({
    type: "LineString",
    features: gokart.ui.features,
    style: fireLineStyle
});


var fireBoundaryStyle = new ol.style.Style({
    stroke: new ol.style.Stroke({
        width: 4.0,
        color: [0, 0, 0, 1.0]
    }),
    fill: new ol.style.Fill({
        color: [0, 0, 0, 0.25]
    })
});

var fireBoundaryDraw = new ol.interaction.Draw({
    type: "Polygon",
    features: gokart.ui.features,
    style: fireBoundaryStyle
});


var snapToLines = new ol.interaction.Snap({
    features: gokart.ui.features,
    edge: true,
    vertex: false,
    pixelTolerance: 16
});

var sssTools = [{
    name: "Hot Spot",
    icon: "static/images/iD-sprite.svg#icon-point",
    interactions: [hotSpotDraw],
    style: hotSpotStyle,
    showName: true
}, {
    name: "Spot Fire",
    icon: "static/images/iD-sprite.svg#icon-point",
    interactions: [spotFireDraw],
    style: spotFireStyle,
    showName: true
}, {
    name: "Division",
    icon: "static/images/iD-sprite.svg#icon-point",
    interactions: [divisionDraw, snapToLines],
    style: divisionStyle,
    showName: true
}, {
    name: "Sector",
    icon: "static/images/iD-sprite.svg#icon-point",
    interactions: [sectorDraw, snapToLines],
    style: sectorStyle,
    showName: true
}, {
    name: "Fire Line Constructed",
    icon: "static/images/iD-sprite.svg#icon-line",
    style: fireLineStyle,
    interactions: [fireLineDraw],
    showName: true
}, {
    name: "Fire Boundary",
    icon: "static/images/iD-sprite.svg#icon-area",
    style: fireBoundaryStyle,
    interactions: [fireBoundaryDraw],
    showName: true
}];

sssTools.forEach(function(tool) {
    gokart.ui.annotations.tools.push(tool);
});

// template for the tracking tab
var trackingList = new Vue({
    el: "#tracking-list-tab",
    data: {
        viewportOnly: true,
        toggleHistory: false,
        selectedOnly: false,
        search: "",
        cql: "",
        history: "",
        fields: ["id", "name", "callsign", "make", "model", "rego", "category", "deviceid", "symbol"],
        allFeatures: [],
        extentFeatures: [],
        historyFromDate: "",
        historyFromTime: "",
        historyToDate: "",
        historyToTime: "",
        historyRangeMilliseconds: 0
    },
    computed: {
        features: function() {
            if (this.viewportOnly) {
                return this.extentFeatures
            } else {
                return this.allFeatures
            };
        },
        selectedFeatures: function() {
            return this.features.filter(this.selected);
        },
        stats: function() {
            return Object.keys(this.extentFeatures).length + "/" + Object.keys(this.allFeatures).length;
        },
        historyRange: {
            get: function() {
                return this.historyRangeMilliseconds
            },
            set: function(val) {
                this.historyRangeMilliseconds = val;
                currentDate = new moment();
                this.historyToDate = currentDate.format('YYYY-MM-DD');
                this.historyToTime = currentDate.format('HH:mm');
                fromDate = currentDate.subtract(val, "milliseconds");
                this.historyFromDate = fromDate.format('YYYY-MM-DD');
                this.historyFromTime = fromDate.format('HH:mm');
            }
        }
    },
    methods: {
        select: function(f) {
            gokart.ui.info.select(f)
        },
        selected: function(f) {
            return gokart.ui.info.selected(f)
        },
        setCQLFilter: function(cql) {
            trackingLayer.cql_filter = cql;
            trackingLayer.olLayer().getSource().loadSource();
        },
        historyCQLFilter: function() {
            historyLayer.cql_filter = "deviceid in (" + gokart.ui.info.sel.join(",") + ") and seen between '" + this.historyFromDate + " " + this.historyFromTime + ":00' and '" + this.historyToDate + " " + this.historyToTime + ":00'";
            gokart.ui.catalogue.onLayerChange(historyLayer, true);
        },
        resourceFilter: function(f) {
            var search = ('' + this.search).toLowerCase();
            var found = !search || this.fields.some(function(key) {
                return ('' + f.get(key)).toLowerCase().indexOf(search) > -1;
            });
            if (this.selectedOnly) {
                return this.selected(f) && found
            };
            return found;
        },
        resourceOrder: function(f1, f2) {
            return f1.get("age") > f2.get("age");
        },
        zoomToSelected: function() {
            var extent = ol.extent.createEmpty();
            this.selectedFeatures.forEach(function(f) {
                ol.extent.extend(extent, f.getGeometry().getExtent());
            });
            gokart.map.getView().fit(extent, gokart.map.getSize());
        }
    }
});


var renderTracking = debounce(function() {
    if (!trackingLayer.olLayer || (trackingLayer.olLayer().getSource().getFeatures().length == 0) || !gokart.mapExportControls) {
        return
    }
    trackingList.extentFeatures = trackingLayer.olLayer().getSource().getFeaturesInExtent(gokart.mapExportControls.mapLayout.extent);
    trackingList.allFeatures = trackingLayer.olLayer().getSource().getFeatures();
}, 100);

gokart.map.getLayerGroup().on("change", renderTracking);
gokart.map.getView().on("propertychange", renderTracking);