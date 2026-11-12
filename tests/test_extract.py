import datetime as dt

from noticeday.extract import extract, initial_end
from noticeday.text import Duration

CONTRACT = """SUPPLY AGREEMENT
This Supply Agreement (the "Agreement") is entered into as of March 1, 2021 (the "Effective Date") by and between A Co. and B Co.
1. Definitions. "Calendar Quarter" means each successive period of three consecutive calendar months.
9. Term. The term of this Agreement shall commence on the Effective Date and continue for a period of two (2) years.
Thereafter this Agreement shall automatically renew for successive one (1) year periods unless either party gives written notice
of non-renewal at least sixty (60) days prior to the expiration of the then-current term.
10. Termination. Either party may terminate this Agreement if the other party fails to cure a breach within thirty (30) days after written notice.
11. Confidentiality. The obligations in this section survive for five (5) years after termination."""


def test_extracts_term_renewal_notice_with_evidence():
    ex = extract(CONTRACT)
    assert ex.get("start_date") == dt.date(2021, 3, 1)
    assert ex.get("term") == Duration(2, "year")
    assert initial_end(ex) == dt.date(2023, 3, 1)
    assert ex.get("renewal") == Duration(1, "year")
    assert ex.get("auto_renew") is True
    assert ex.get("notice") == Duration(60, "day")
    assert "sixty (60) days" in ex.quote("notice")


def test_mutual_extension_is_not_a_renewal():
    ex = extract("The term of this Agreement is one (1) year from January 1, 2020. "
                 "The term may be extended for one (1) year periods by mutual written agreement of the parties.")
    assert ex.get("renewal") is None and ex.get("auto_renew") is None


def test_perpetual_and_explicit_end():
    assert extract("This Agreement shall commence on the Effective Date and continue until terminated by either party.").get("end_date") == "perpetual"
    assert extract("This Agreement shall begin on the Effective Date and shall continue until December 31, 2020.").get("end_date") == dt.date(2020, 12, 31)
