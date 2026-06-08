from app.vendors.semiconductors.schemas import RawSemiconductorCandidate

class STClient:
    def search_mosfets(self, req):
        return [
            RawSemiconductorCandidate(manufacturer="ST", mpn="STW62N65M5", category="MOSFET", technology="Si", vds_v=650, current_cont_a=45, rds_on_ohm=0.060, qg_nc=82, tr_ns=23, tf_ns=18, package="TO-247", lifecycle="Active", source_type="manufacturer"),
            RawSemiconductorCandidate(manufacturer="ST", mpn="SCT040H65G3AG", category="MOSFET", technology="SiC", vds_v=650, current_cont_a=37, rds_on_ohm=0.040, qg_nc=62, tr_ns=13, tf_ns=11, package="HiP247", lifecycle="Active", source_type="manufacturer"),
        ]
