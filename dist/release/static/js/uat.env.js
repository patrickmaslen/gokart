var env = {
    envType:"uat",
    envVersion:"2007-09-08 10:26",
    appType: (window.location.protocol == "file:")?"cordova":"webapp",

    cswService:"https://oim.dbca.wa.gov.au/catalogue/api/records/",
    catalogueAdminService:"https://oim.dbca.wa.gov.au",

    wmtsService:"https://kmi.dbca.wa.gov.au/geoserver/gwc/service/wmts",
    wmsService:"https://kmi.dbca.wa.gov.au/geoserver/wms",
    wfsService:"https://kmi.dbca.wa.gov.au/geoserver/wfs",
    legendSrc:"https://kmi.dbca.wa.gov.au/geoserver/gwc/service/wms?REQUEST=GetLegendGraphic&VERSION=1.0.0&FORMAT=image/png&LAYER=",

    gokartService:"https://sss-uat.dbca.wa.gov.au",
    resourceTrackingService:"https://resourcetracking-uat.dbca.wa.gov.au",
    bfrsService:"https://bfrs-uat.dbca.wa.gov.au",
    staticService:"https://static.dbca.wa.gov.au",

    s3Service:"http://gokart.dpaw.io/",

    bushfireLayer:"dpaw:bushfire_latest_uat",
    finalFireboundaryLayer:"dpaw:bushfire_final_fireboundary_latest_uat",
    fireboundaryLayer:"dpaw:bushfire_fireboundary_latest_uat",

    allBushfireLayer:"dpaw:bushfire_uat",
    allFireboundaryLayer:"dpaw:bushfire_fireboundary_uat"

}


document.body.onload = function() {
    var setStyle = function (){
        var leftPanel = document.getElementById("offCanvasLeft");
        if (leftPanel) {
            leftPanel.style = "background-image:url('dist/static/images/uat.svg');background-size:cover;background-repeat:no-repeat;background-position:center center;"
        } else {
            setTimeout(setStyle,500)
        }
    }
    setTimeout(setStyle,500)
}
