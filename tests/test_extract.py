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


def test_renewal_limit():
    ex = extract("The term of this Agreement is twelve (12) months from the date hereof, and will be automatically renewed "
                 "for one (1) additional twelve month period unless either party shall notify the other in writing.")
    assert ex.get("renewal_limit") == 1 and ex.get("renewal") == Duration(12, "month")
    ex = extract("The initial term of this Agreement is five (5) years. Thereafter this Agreement shall automatically renew "
                 "for successive one (1) year periods unless either party gives sixty (60) days notice.")
    assert ex.get("renewal_limit") is None
    ex = extract("This Agreement shall automatically renew for up to three (3) additional periods of twelve (12) months each.")
    assert ex.get("renewal_limit") == 3


def test_option_notice_only_when_renewal_is_not_automatic():
    ex = extract("The Initial Term of this Agreement is three (3) years. If Distributor wishes to extend the term beyond the "
                 "Initial Term, it must notify Supplier in writing at least six (6) months prior to the end of the Initial Term.")
    assert ex.get("option_notice") == Duration(6, "month")
    assert extract(CONTRACT).get("option_notice") is None


def test_term_counted_from_effective_date():
    # "after"/"following"/"thereafter" next to a term length is not a survival clause.
    assert extract("This Agreement shall commence on the Effective Date and continue for a period of three (3) "
                   "years after the Effective Date.").get("term") == Duration(3, "year")
    assert extract("This Agreement shall commence on the Effective Date and continue thereafter for a period of "
                   "two (2) years, unless sooner terminated.").get("term") == Duration(2, "year")
    assert extract("Unless sooner terminated, this Agreement will continue in full force beginning on the Effective "
                   "Date and ending two (2) years thereafter.").get("term") == Duration(2, "year")


def test_survival_and_event_terms_are_not_the_term():
    ex = extract("During the term of this Agreement and for a period of two (2) years thereafter, Supplier shall not "
                 "compete with Buyer.")
    assert ex.get("term") is None
    ex = extract("This Agreement shall commence on the Effective Date and shall remain in full force for ten (10) years "
                 "after the First Commercial Sale of the first Licensed Product.")
    assert ex.get("term") is None
    ex = extract("The term of this Agreement shall be one (1) year. Contractor and Customer will meet every three (3) "
                 "months during the term of this Agreement.")
    assert ex.get("term") == Duration(1, "year")


def test_more_ways_to_state_the_end():
    assert extract("Unless earlier terminated, this Agreement shall take effect on December 1st, 2015 and shall "
                   "expire on November 30, 2016.").get("end_date") == dt.date(2016, 11, 30)
    assert extract("The initial term of the Services shall continue up to and including 28 February 2000.").get(
        "end_date") == dt.date(2000, 2, 28)
    assert extract("TERM: November 01, 2014 to October 31, 2017").get("end_date") == dt.date(2017, 10, 31)


def test_more_ways_to_state_a_renewal():
    def ren(t):
        return extract(t).get("renewal")
    assert ren("The term of this Agreement shall be one (1) year commencing on the Effective Date and automatically "
               "renewing annually thereafter, unless either party provides notice.") == Duration(1, "year")
    assert ren("This Agreement will extend automatically for monthly periods unless either party notifies the other "
               "party in writing at least thirty (30) days before the expiration of the then current term.") == Duration(1, "month")
    assert ren("This Agreement shall automatically renew beyond the Initial Term for successive one (I) year terms.") == Duration(1, "year")
    assert ren("The Initial Term shall automatically be extended for an additional period of half a year unless "
               "either party provides notice.") == Duration(6, "month")
    ex = extract("The initial term of this Agreement is five (5) years. Upon expiry of the Initial Term this Agreement "
                 "shall automatically renew for successive terms of the same duration, unless either party gives notice.")
    assert ex.get("renewal") == Duration(5, "year")


def test_start_date_skips_filing_footers_and_other_documents():
    ex = extract("Source: ACME MEDICAL, INC., 10-K, 3/21/2019 EXHIBIT 10.4 THIS AGREEMENT is made on March 1, 2018 "
                 "between A and B.")
    assert ex.get("start_date") == dt.date(2018, 3, 1)
    ex = extract("Supply Agreement. Reference is made to the EPC Agreement dated September 30, 2009 (the \"EPC Agreement\"). "
                 "Nothing else is dated.")
    assert ex.get("start_date") is None
    ex = extract("This Agreement is dated May 4, 2017 (the \"Effective Date\") between A and B.")
    assert ex.get("start_date") == dt.date(2017, 5, 4)


def test_notice_for_stopping_a_continuation():
    ex = extract("After the Initial Term, this Agreement shall continue on a month to month basis until terminated by "
                 "either party upon thirty (30) days prior written notice to the other.")
    assert ex.get("notice") == Duration(30, "day")
    ex = extract("Upon expiration of the Initial Term, this Agreement shall automatically renew for consecutive one (1) "
                 "year periods, unless terminated by Reseller within sixty (60) days prior to the expiration of the term.")
    assert ex.get("notice") == Duration(60, "day")
    # A cure period is still not a notice period.
    ex = extract("This Agreement shall automatically renew for successive one (1) year terms. Either party may terminate "
                 "if the other fails to cure a breach within thirty (30) days after written notice.")
    assert ex.get("notice") is None


def test_term_lengths_are_not_notice_periods_or_initial_terms():
    ex = extract("The Term shall automatically renew thereafter for successive 5-year terms unless either party provides "
                 "prior written notice of termination not less than 90 days prior to the end of such five-year term.")
    assert ex.get("notice") == Duration(90, "day")
    ex = extract("The term of this Agreement shall be determined in writing by the parties hereto in respect of any "
                 "subsequent one year renewal term.")
    assert ex.get("term") is None


FILLER = "The parties shall cooperate in good faith. " * 80  # pushes later text past the preamble


def test_start_date_named_effective_date_wins():
    # The date the contract labels "Effective Date" beats a later "effective" date of another document.
    ex = extract("THIS IP AGREEMENT is entered into as of April 14, 2014 (the \"Effective Date\"), by and between A and B. "
                 + FILLER + "\"License\" means the License Agreement between A and C, effective as of July 31, 2010.")
    assert ex.get("start_date") == dt.date(2014, 4, 14)
    # A labelled date in the term section, far from the preamble, beats the signing date.
    ex = extract("This Strategic Alliance Agreement is entered into as of December 27, 2011 by and among A and B. " + FILLER
                 + "11.1 Term. This Agreement shall be effective as of January 1, 2012 (the \"Effective Date\").")
    assert ex.get("start_date") == dt.date(2012, 1, 1)
    ex = extract("This agreement (\"Agreement\") is entered into on April 15 , 2010 (\"EffectiveDate\") by and between A and B.")
    assert ex.get("start_date") == dt.date(2010, 4, 15)
