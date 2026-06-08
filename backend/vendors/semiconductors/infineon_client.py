from app.vendors.semiconductors.schemas import RawSemiconductorCandidate

class InfineonClient:
    def search_mosfets(self, req):
        return [
            RawSemiconductorCandidate(manufacturer="Infineon", mpn="IPW60R045P7", category="MOSFET", technology="Si", vds_v=600, current_cont_a=46, rds_on_ohm=0.045, qg_nc=78, tr_ns=21, tf_ns=16, package="TO-247", lifecycle="Active", source_type="manufacturer"),
            RawSemiconductorCandidate(manufacturer="Infineon", mpn="IMW65R072M1H", category="MOSFET", technology="SiC", vds_v=650, current_cont_a=36, rds_on_ohm=0.072, qg_nc=34, tr_ns=16, tf_ns=13, package="TO-247", lifecycle="Active", source_type="manufacturer"),
        ]
