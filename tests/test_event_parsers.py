"""Parsers for event emails and the Genève internationale newsletter, from synthetic text that follows the real patterns."""
from harness.event_parsers import extract_date_range, parse_club_subject, parse_geneve_int, parse_luma, parse_registration, is_registration_confirmation
from datetime import date


def test_club_subjects_give_title_date_time_and_venue():
    r = parse_club_subject("📨 Invitation | Anticipatory Leadership Lab with GESDA, 17 September 2026 at 16:30")
    assert (r["kind"], r["title"], r["start"], r["venue"], r["all_day"]) == ("invitation", "Anticipatory Leadership Lab with GESDA", "2026-09-17T16:30:00+02:00", None, False)
    r = parse_club_subject("📨 Invitation | Visit to the Federal Palace, 16 June 2026 at 16:30, Bern")
    assert (r["title"], r["venue"]) == ("Visit to the Federal Palace", "Bern")
    r = parse_club_subject("📨 Reminder | Luncheon-debate with Someone Famous, 25 August 2026 at 12:00")
    assert r["kind"] == "reminder" and r["title"] == "Luncheon-debate with Someone Famous"
    r = parse_club_subject("📨 Invitation | Diplomacy Day at the Locarno Film Festival, 10 August 2026")
    assert r["all_day"] is True and r["start"] == "2026-08-10"
    r = parse_club_subject("📨 Reminder | General Assembly & Evening, 8 May 2026 from 17:30, Domaine du Grand-Saconnex")
    assert r["start"] == "2026-05-08T17:30:00+02:00" and r["venue"].startswith("Domaine")
    assert parse_club_subject("📨 Invitation | Closed-door Discussion at the GCSP, 1st April 2026 at 12:30")["start"] == "2026-04-01T12:30:00+02:00"
    assert parse_club_subject("Information | AI in Multilateral Diplomacy, 22 April 2026 at 18:30, Campus Biotech")["kind"] == "information"
    assert parse_club_subject("📬 Newsletter | Upcoming Events | New Articles") is None and parse_club_subject("📬 Club News | Summer Edition") is None
    assert parse_club_subject("📨 Invitation | Winter visit, 5 January 2027 at 09:00")["start"] == "2027-01-05T09:00:00+01:00"          # winter time


def test_luma_registrations_read_title_status_time_zone_and_venue():
    snip = "Some Person You've got a spot at Digital International Geneva - Monthly Thematic Session OCT 5 Monday, October 5 5:15 PM - 6:45 PM GMT+2 Giga Connectivity Centre ↗ Genève, Switzerland Event Page"
    r = parse_luma("Registration approved for Digital International Geneva - Monthly Thematic Session", snip, "2026-10-02T06:24:41Z")
    assert (r["what"], r["title"], r["start"], r["end"], r["venue"]) == ("approved", "Digital International Geneva - Monthly Thematic Session", "2026-10-05T17:15:00+02:00", "2026-10-05T18:45:00+02:00", "Giga Connectivity Centre")
    multi = "GenAI Zürich You have registered for GenAI Zürich 2026 APR 1 Wednesday, April 1 8:00 AM - Apr 2, 6:00 PM GMT+2 Volkshaus Zürich ↗ Zürich Conference Pass Free Event Page"
    r = parse_luma("Registration confirmed for GenAI Zürich 2026", multi, "2026-03-31T15:00:34Z")
    assert (r["start"], r["end"], r["venue"]) == ("2026-04-01T08:00:00+02:00", "2026-04-02T18:00:00+02:00", "Volkshaus Zürich")
    z = parse_luma("Registration confirmed for aiLights - Building with Apertus", "aiLights You have registered for x JAN 13 Tuesday, January 13, 2026 9:00 AM - 9:45 AM GMT+1 Zoom Hoi and Welcome!", "2025-12-19T09:22:20Z")
    assert z is None or z["online"]                                                                                                       # a different date layout: either skipped or read as online
    p = parse_luma("Registration pending approval for X Event", "A B You've asked to join X Event DEC 3 Thursday, December 3 6:00 PM - 8:00 PM GMT+1 Somewhere ↗", "2026-11-20T10:00:00Z")
    assert p["what"] == "pending approval" and p["start"] == "2026-12-03T18:00:00+01:00"
    jan = parse_luma("Registration approved for New Year Do", "A B You've got a spot at New Year Do JAN 9 Saturday, January 9 7:00 PM - 9:00 PM GMT+1 Bar", "2026-12-28T10:00:00Z")
    assert jan["start"].startswith("2027-01-09")                                                                                         # an email in December for a January event
    assert parse_luma("Welcome to our newsletter", "x", "2026-10-02T00:00:00Z") is None


def test_date_ranges_in_free_text():
    h = date(2026, 7, 1)
    assert extract_date_range("Dates: 14-15 October 2026 Venue: PALEXPO", h) == ("2026-10-14", "2026-10-15")
    assert extract_date_range("Dates: Monday, 4 May to Friday, 8 May 2026 Venue", h) == ("2026-05-04", "2026-05-08")
    assert extract_date_range("on 14 October 2026 at the", h) == ("2026-10-14", None)
    assert extract_date_range("it takes place October 14-15, 2026 in", h) == ("2026-10-14", "2026-10-15")
    assert extract_date_range("on 1st April 2026", h) == ("2026-04-01", None) and extract_date_range("no date here", h) is None
    assert extract_date_range("31 February 2026", h) is None


def test_organiser_registration_confirmations():
    assert is_registration_confirmation("Registration Confirmed - GESDA - The Anticipation Summit 2026")
    assert is_registration_confirmation("Geneva Cyber Week 2026 - Registration Confirmation and Information")
    assert not is_registration_confirmation("Booking confirmation") and not is_registration_confirmation("Your order is confirmed")
    r = parse_registration("Registration Confirmed - GESDA - The Anticipation Summit 2026", "Your registration is confirmed: Registration Details GESDA - The Anticipation Summit 2026 Dates: 14-15 October 2026 Venue: PALEXPO", "2026-07-01T13:35:22Z")
    assert r["title"] == "GESDA - The Anticipation Summit 2026" and (r["start"], r["end"]) == ("2026-10-14", "2026-10-16")
    r = parse_registration("Geneva Cyber Week 2026 - Registration Confirmation and Information", "We are writing to confirm your registration. Dates: Monday, 4 May to Friday, 8 May 2026 Venue: CICG", "2026-04-30T13:39:17Z")
    assert r["title"] == "Geneva Cyber Week 2026" and r["start"] == "2026-05-04"
    assert parse_registration("Registration Confirmed - Some Event", "Dear Anne-Marie, thanks, see you soon", "2026-04-30T13:39:17Z") is None        # no date: left for the model step


GI_HTML = """<html><body><table><tr><td>Upcoming Events 14-20 September 2026</td></tr></table>
<table><tbody><tr><td>Environment and Sustainable Development </td></tr></tbody></table>
<table><thead><tr><th> Organizer <th> Event <th> Date <th> Location <th> Link </thead>
<tr><!--[if !mso]><!--><td><img src="x" alt="Logo WMO"></td><!--<![endif]-->
<!--[if mso]><td><img src="y" alt="Logo WMO"></td><![endif]-->
<td><table><tr><td><span></span></td></tr></table><table><tr><td><a href="https://wmo.int/events/a">WMO High-level Dialogue on Climate Science</a></td></tr></table></td>
<td> 14.09.2026 <br> 18.09.2026 </td>
<td><table><tr><td><img alt="Location" src="l"></td><td><span>Hybrid</span></td></tr></table></td>
<td><a href="https://wmo.int/events/a"><img alt="Link" src="k"></a></td></tr>
<tr><td><img alt="stockholm_convention logo" src="z"></td>
<td><a href="https://brsmeas.org/e">11th Expert Group Meeting on DDT</a></td><td>14.09.2026<br>16.09.2026</td>
<td><img alt="Location" src="l"><span>International Environment House - II</span></td><td><a href="https://brsmeas.org/e">x</a></td></tr></table>
<table><tbody><tr><td>Digital and Technology</td></tr></tbody></table>
<table><thead><tr><th>Organizer<th>Event<th>Date<th>Location<th>Link</thead>
<tr><td><img alt="Logo ITU" src="i"></td><td><a href="https://itu.int/ai">AI Governance Day</a></td><td>16.09.2026</td><td><img alt="Location" src="l"><span>Online</span></td><td><a href="https://itu.int/ai">x</a></td></tr></table>
</body></html>"""


def test_the_geneve_internationale_tables_are_read_with_themes_organizers_dates_and_places():
    rows = parse_geneve_int(GI_HTML)
    assert len(rows) == 3
    a, b, c = rows
    assert (a["theme"], a["organizer"], a["title"], a["start"], a["end"], a["location"], a["url"]) == (
        "Environment and Sustainable Development", "WMO", "WMO High-level Dialogue on Climate Science", "2026-09-14", "2026-09-18", "Hybrid", "https://wmo.int/events/a")
    assert (b["organizer"], b["location"], b["end"]) == ("stockholm_convention", "International Environment House - II", "2026-09-16")
    assert (c["theme"], c["title"], c["start"], c["end"], c["location"]) == ("Digital and Technology", "AI Governance Day", "2026-09-16", "2026-09-16", "Online")
    assert parse_geneve_int("") == [] and parse_geneve_int("<html>nothing</html>") == []


# ------------------------------------------------------------------ public web pages
GI_WEB = """<table><thead><tr><th>Organizer</th></tr></thead><tbody>
<tr><td class="views-field views-field-field-organizer-logo"><div class="wrapper-image"><img src="x.png" alt="UN HRC" /></div></td>
<td class="views-field views-field-field-title"><div class="taxonomy-term"><span class="bullet"></span></div><div class="event-title">Human Rights Council / HRC 63rd session</div></td>
<td class="views-field views-field-field-date"><time datetime="2026-09-07T12:00:00Z" class="datetime">07.09.2026</time><br><time datetime="2026-10-07T12:00:00Z">07.10.2026</time><br></td>
<td class="views-field views-field-event-address">Palais des Nations </td>
<td class="views-field views-field-field-link"><a href="https://hrc63.sched.com/" target="_blank">https://hrc63.sched.com/</a> </td></tr>
<tr><td><img alt="GESDA_Logo.png"></td><td><div class="event-title">The Anticipation Summit</div></td><td><time datetime="2026-10-14T12:00:00Z">14.10.2026</time><br><time datetime="2026-10-15T12:00:00Z">15.10.2026</time></td>
<td class="views-field-event-address">Palexpo Geneva</td><td class="views-field-field-link"><a href="https://gesda.global/?a=1&amp;b=2">x</a></td></tr>
<tr><td>no title here</td></tr></tbody></table>"""


def test_the_geneve_internationale_calendar_page():
    from harness.event_parsers import parse_geneve_int_web
    rows = parse_geneve_int_web(GI_WEB)
    assert rows[0] == {"title": "Human Rights Council / HRC 63rd session", "start": "2026-09-07", "end": "2026-10-07", "organizer": "UN HRC", "venue": "Palais des Nations", "url": "https://hrc63.sched.com/"}
    assert (rows[1]["organizer"], rows[1]["url"]) == ("GESDA", "https://gesda.global/?a=1&b=2") and len(rows) == 2 and parse_geneve_int_web("") == []


CLUB_WEB = """<article id="post-1"><a href="https://club/x" title="t"></a><div><p>ANG</p><h6><a href="https://club/dialogue-sierra-leone/" rel="bookmark">Dialogue exclusif avec le Président de la Sierra Leone </a></h6>
<p>lundi 12 octobre 2026</p><p>Portail des Nations</p></div></article>
<article id="post-2"><div><p>ANG/FR</p><h6><a href="https://club/visite/">Visite privée &ndash; Grand Prix d&rsquo;Horlogerie</a></h6><p>mardi 3 novembre 2026</p><p>Musée d'art et d'histoire (MAH)</p></div></article>
<article id="post-3"><h6><a href="https://club/undated/">No date line</a></h6><p>Somewhere</p></article>"""


def test_the_club_diplomatique_events_page():
    from harness.event_parsers import parse_club_events
    rows = parse_club_events(CLUB_WEB)
    assert rows[0] == {"title": "Dialogue exclusif avec le Président de la Sierra Leone", "start": "2026-10-12", "end": None, "organizer": "Club Diplomatique de Genève", "venue": "Portail des Nations", "url": "https://club/dialogue-sierra-leone/"}
    assert rows[1]["title"] == "Visite privée – Grand Prix d’Horlogerie" and rows[1]["start"] == "2026-11-03" and rows[1]["venue"] == "Musée d'art et d'histoire (MAH)" and len(rows) == 2


UNOG = """<table><tr><td><p><strong>Committee on the Rights of the Child</strong></p><p><a href="https://x/sess?a=1&amp;b=2">100th session</a></p></td><td>12-Jan</td><td>30-Jan</td></tr>
<tr><td><strong>World Health Assembly</strong><br><a href="https://who/wha">79th session</a></td><td><span>18-May</span></td><td><span>23-May</span></td></tr>
<tr><td><strong>Conference on Disarmament</strong></td><td>&nbsp;11-May</td><td>26-June</td></tr><tr><td>Header</td><td>Start</td><td>End</td></tr></table>"""


def test_the_un_geneva_calendar_of_major_meetings():
    from harness.event_parsers import parse_unog
    rows = parse_unog(UNOG, 2026)
    assert [(r["title"], r["start"], r["end"]) for r in rows] == [("Committee on the Rights of the Child – 100th session", "2026-01-12", "2026-01-30"), ("World Health Assembly – 79th session", "2026-05-18", "2026-05-23"),
                                                                    ("Conference on Disarmament", "2026-05-11", "2026-06-26")]
    assert rows[0]["url"] == "https://x/sess?a=1&b=2" and rows[0]["venue"] == "Palais des Nations"
