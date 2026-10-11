"""Offline evidence renderer contracts using the frontend Node VM harness pattern."""

from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


class Markup(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)

    def with_class(self, name):
        return [(tag, attrs) for tag, attrs in self.elements
                if name in attrs.get("class", "").split()]


def fixture():
    terms = [{"term": f"risk {i}", "category": "financial_crime", "score": .7}
             for i in range(10)]
    bias = {"label": "Mixed", "score": .3, "total_sentences": 2,
            "bias_types": [{"label": "Loaded language", "count": 1}],
            "sentences": [
                {"text": "Shocking claim.", "biased": True,
                 "spans": [{"start": 0, "end": 8, "type": "loaded_language"}]},
                {"text": "A neutral sentence.", "biased": False, "spans": []}]}
    articles = [
        {"title": "First report", "source": "Primary Source", "date": "2025-12-01",
         "url": "https://example.org/first?a=1&b=2", "severity": .9,
         "category_keys": ["financial_crime"],
         "categories": [{"key": "financial_crime", "label": "Financial Crime"}],
         "risk_terms": terms, "bias": deepcopy(bias)},
        {"title": "Second report", "source": "Second Source", "date": "2026-01-03",
         "url": "javascript:alert(1)", "severity": .85,
         "category_keys": ["financial_crime", "regulatory"],
         "categories": [{"key": "financial_crime", "label": "Financial Crime"}],
         "risk_terms": [deepcopy(terms[0]), deepcopy(terms[0]),
                        {"term": "alternative", "category": "regulatory", "score": .6}],
         "bias": {**deepcopy(bias), "score": .8, "label": "Polarized"}},
        {"title": "Third report", "source": "Third Source", "date": "2026-01-09",
         "url": None, "severity": .2, "category_keys": ["regulatory"], "categories": [],
         "risk_terms": [{"term": "other", "category": "regulatory", "score": .2}],
         "bias": {"label": "Factual", "score": 0, "total_sentences": 1,
                  "sentences": [{"text": "Routine filing.", "biased": False, "spans": []}]}}
    ]
    return {
        "supplier": {"name": "Example Entity", "country": "US", "entity_type": "organization",
                     "status": "verified", "identity_confidence": .95},
        "risk": {"score": 28, "level": "medium", "contributions": [],
                 "coverage_assessment": {"complete": True, "missing_sources": []}},
        "sanctions": {"available": True, "match": False, "list_size": 100},
        "litigation": {"available": True, "cases": [{"case": "Recorded case", "court": "Court",
                                                    "date": "2026-01-01", "url": "https://example.org/case"}]},
        "adverse_media": articles, "media_summary": {"total": 3, "categories": [], "bias": {}},
        "ownership": [], "entity_resolution": {}, "graph": {},
        "agent_summary": {"summary": "Source-backed summary.", "recommendation": "Review required."},
        "sources_consulted": {"ofac": True, "gdelt": True, "courtlistener": True},
    }


HARNESS = r"""
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const stop=new Error('stop startup'),nodes=new Map();
const context=vm.createContext({URL,AbortController,setTimeout,clearTimeout,
  window:{addEventListener(){},scrollTo(){}},
  document:{getElementById(){throw stop;}}});
try{vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);}
catch(error){if(error!==stop)throw error;}
let focused='';
function makeNode(id){
  const classes=new Set();
  return {id,value:id==='sortSel'?'severity':'',textContent:'',checked:false,hidden:false,
    dataset:{},attrs:{},style:{},_html:'',children:[],tabIndex:-1,
    classList:{add(k){classes.add(k);},contains(k){return classes.has(k);},
      toggle(k,on){if(on===undefined)on=!classes.has(k);on?classes.add(k):classes.delete(k);return on;}},
    setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},
    focus(){focused=this.id;context.document.activeElement=this;},
    closest(){return {querySelector(){return node('scopeLabel');}};},
    querySelector(){return null;},
    querySelectorAll(selector){return selector==='details[open]'?this.children.filter(n=>n.open):[];},
    get innerHTML(){return this._html;},
    set innerHTML(html){
      this._html=html;this.children=[];
      if(id==='biasTable')for(const match of html.matchAll(/<details\b([^>]*)>/g)){
        const key=/\bid="([^"]+)"/.exec(match[1])[1],detail=makeNode(key);
        detail.open=/\sopen(?:\s|$)/.test(match[1]);nodes.set(key,detail);this.children.push(detail);
      }
    }};
}
function node(id){if(!nodes.has(id))nodes.set(id,makeNode(id));return nodes.get(id);}
const keys=['media','signals','records'];
const tabs=keys.map(key=>Object.assign(makeNode('evidence-tab-'+key),{dataset:{evidenceTab:key}}));
const panels=keys.map(key=>Object.assign(makeNode('evidence-panel-'+key),{dataset:{evidencePanel:key}}));
node('view2').querySelectorAll=selector=>selector==='[data-evidence-tab]'?tabs:selector==='[data-evidence-panel]'?panels:[];
context.document.getElementById=node;
context.document.querySelectorAll=()=>[];
context.node=node;context.fixture=input.data;context.tabs=tabs;context.panels=panels;
context.tabState=()=>({selected:tabs.filter(t=>t.attrs['aria-selected']==='true').map(t=>t.dataset.evidenceTab),
  visible:panels.filter(p=>!p.hidden).map(p=>p.dataset.evidencePanel),
  stops:tabs.filter(t=>t.tabIndex===0).map(t=>t.dataset.evidenceTab),focused});
vm.runInContext("DATA=fixture;DATA_ORIGIN='live';",context);
(async()=>{
  const result=await vm.runInContext('(async()=>{'+input.script+'})()',context);
  process.stdout.write(JSON.stringify(result));
})().catch(error=>{process.stderr.write(String(error.stack));process.exitCode=1;});
"""


@unittest.skipUnless(NODE, "Node is required for renderer tests")
class EvidenceRenderingTests(unittest.TestCase):
    def test_search_for_same_subject_preserves_completed_form_details(self):
        result = self.run_js("""
TYPE='organization';node('entSearch').value='Anthropic';node('f_name').value='Anthropic';
node('f_country').value='United States';node('f_reg').value='984500B6DEB8CEBC4Z70';
runInvestigation=()=>true;startEntitySearch('organization');
return {country:node('f_country').value,registration:node('f_reg').value};
""")
        self.assertEqual(result, {"country": "United States",
                                  "registration": "984500B6DEB8CEBC4Z70"})

    def test_empty_media_distinguishes_source_outage_from_no_results(self):
        data = fixture()
        data["adverse_media"] = []
        data["sources_consulted"] = {"gdelt": False}
        result = self.run_js("renderResults();return {html:node('resultsList').innerHTML,count:node('mediaCount').textContent};", data)
        self.assertIn("did not respond", result["html"])
        self.assertEqual(result["count"], "Live media source unavailable")
        data["sources_consulted"]["gdelt"] = True
        html = self.run_js("renderResults();return node('resultsList').innerHTML;", data)
        self.assertIn("No adverse headlines were returned", html)
        self.assertNotIn("selected filters", html)

    def test_lei_in_aliases_moves_to_registration_without_losing_names(self):
        result = self.run_js("""
TYPE='organization';node('f_reg').value='';
node('f_aliases').value='Anthropic AI, 984500b6deb8cebc4z70';
normalizeInvestigationIdentifier();
return {registration:node('f_reg').value,aliases:node('f_aliases').value};
""")
        self.assertEqual(result, {"registration": "984500B6DEB8CEBC4Z70",
                                  "aliases": "Anthropic AI"})

    def test_identifier_normalization_preserves_explicit_registration_and_people(self):
        result = self.run_js("""
TYPE='organization';node('f_reg').value='ABC-123';
node('f_aliases').value='984500B6DEB8CEBC4Z70';normalizeInvestigationIdentifier();
const company=node('f_reg').value;
TYPE='individual';node('f_reg').value='';normalizeInvestigationIdentifier();
return {company,person:node('f_reg').value,aliases:node('f_aliases').value};
""")
        self.assertEqual(result, {"company": "ABC-123", "person": "",
                                  "aliases": "984500B6DEB8CEBC4Z70"})

    def test_unknown_search_offers_live_actions_and_escapes_query(self):
        html = self.run_js("""
node('entSearch').value='Anthropic <img src=x>';
SUBJECTS_LIST=[];ENT_FILTER='all';renderEntityList();
return {actions:node('entitySearchActions').innerHTML,list:node('entList').innerHTML};
""")
        self.assertIn("Search company", html["actions"])
        self.assertIn("Search person", html["actions"])
        self.assertIn("&lt;img src=x&gt;", html["actions"])
        self.assertNotIn("<img", html["actions"])
        self.assertIn("No sample cases match", html["list"])

    def test_live_search_resets_stale_details_and_uses_selected_type(self):
        result = self.run_js("""
node('entSearch').value='  Ada Lovelace  ';
for(const id of ['f_aliases','f_dob','f_reg','f_country','f_city','f_website','f_address'])node(id).value='Previous subject';
let calls=0;runInvestigation=()=>{calls++;return 'started';};
const started=startEntitySearch('individual');
return {started,calls,type:TYPE,name:node('f_name').value,
 details:['f_aliases','f_dob','f_reg','f_country','f_city','f_website','f_address'].map(id=>node(id).value)};
""")
        self.assertEqual(result, {"started": "started", "calls": 1,
                                  "type": "individual", "name": "Ada Lovelace",
                                  "details": [""] * 7})

    def test_empty_search_and_invalid_type_do_not_start_a_request(self):
        result = self.run_js("""
let calls=0;runInvestigation=()=>calls++;
node('entSearch').value=' ';startEntitySearch('organization');renderEntityList();
const empty=node('entitySearchActions').innerHTML;
node('entSearch').value='Anthropic';startEntitySearch('invalid');
ENT_FILTER='organization';renderEntityList();
return {calls,empty,actions:node('entitySearchActions').innerHTML};
""")
        self.assertEqual(result["calls"], 0)
        self.assertEqual(result["empty"], "")
        self.assertIn("Search company", result["actions"])
        self.assertNotIn("Search person", result["actions"])

    def run_js(self, script, data=None):
        result = subprocess.run(
            [NODE, "-e", HARNESS, str(ROOT / "static" / "app.js")],
            input=json.dumps({"data": fixture() if data is None else data, "script": script}),
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_risk_summary_is_semantic_and_keeps_full_scope(self):
        result = self.run_js("""
renderDashboard();const before=node('riskbox').innerHTML;
toggleTerm('other');return {before,after:node('riskbox').innerHTML,
  overview:node('riskbox').classList.contains('risk-overview'),title:node('rTab').textContent,
  meta:node('caseMeta').innerHTML,count:node('mediaCount').textContent};
""")
        markup = Markup(result["before"])
        self.assertTrue(result["overview"])
        self.assertEqual(len(markup.with_class("risk-score-block")), 1)
        self.assertEqual([tag for tag, _ in markup.with_class("risk-facts")], ["dl"])
        self.assertEqual(sum(tag == "dt" for tag, _ in markup.elements), 4)
        self.assertIn("Overall risk", result["before"])
        self.assertIn("3 articles", result["before"])
        self.assertIn("1 docket<", result["before"])
        self.assertIn("Review required.", result["before"])
        self.assertEqual(result["before"], result["after"])
        self.assertIn("1 of 3", result["count"])
        self.assertEqual(result["title"], "Example Entity")
        self.assertIn("Live request", result["meta"])

    def test_unavailable_checks_and_missing_required_sources_are_not_clearance(self):
        data = fixture()
        data["sanctions"].update(available=False, list_size=0)
        data["litigation"] = {"available": False, "cases": []}
        data["sources_consulted"] = {"ofac": False, "gdelt": False, "courtlistener": False}
        data["risk"]["coverage_assessment"] = {"complete": False,
            "missing_sources": ["ofac", "gdelt", "courtlistener", "<img src=x>"]}
        result = self.run_js("renderDashboard();return {risk:node('riskbox').innerHTML,lit:node('litigation').innerHTML};", data)
        self.assertGreaterEqual(result["risk"].count("Unavailable / not screened"), 3)
        self.assertNotIn("0 dockets", result["risk"])
        self.assertNotIn("No match", result["risk"])
        for source in ("OFAC", "GDELT", "COURTLISTENER"):
            self.assertIn(source, result["risk"])
        self.assertIn("Missing required sources:", result["risk"])
        self.assertIn("not a clearance", result["risk"])
        self.assertNotIn("<IMG", result["risk"])
        self.assertIn("Unavailable / not screened", result["lit"])

    def test_sample_and_escaped_entity_metadata_are_preserved(self):
        data = fixture()
        hostile = '<img src=x onerror="alert(1)">'
        data["supplier"].update(name=hostile, country=hostile, entity_type=hostile, status=hostile)
        data["agent_summary"]["recommendation"] = hostile
        result = self.run_js("DATA_ORIGIN='sample';renderDashboard();return {meta:node('caseMeta').innerHTML,risk:node('riskbox').innerHTML,title:node('rTab').textContent};", data)
        self.assertEqual(result["title"], hostile)
        for key in ("meta", "risk"):
            self.assertNotIn("<img", result[key])
            self.assertIn("&lt;img", result[key])
        self.assertIn("Sample / offline", result["meta"])
        self.assertIn("no live source checks", result["risk"])

    def test_terms_are_ranked_compact_and_count_articles_not_occurrences(self):
        result = self.run_js("renderCloud();return {html:node('cloud').innerHTML,count:node('cloudCount').textContent};")
        rows = Markup(result["html"]).with_class("term-row")
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(tag == "button" and a["type"] == "button" for tag, a in rows))
        self.assertEqual(rows[0][1]["data-term"], "risk 0")
        self.assertEqual(rows[0][1]["aria-label"], "risk 0: 2 articles")
        self.assertTrue(all(a["aria-pressed"] == "false" for _, a in rows))
        self.assertIn("Show all 12 terms", result["html"])
        self.assertEqual(result["count"], "12 terms")
        self.assertNotIn("font-size", result["html"])

    def test_term_facets_retain_alternatives_and_other_filters_apply(self):
        result = self.run_js("""
F.terms.add('risk 0');renderCloud();toggleTermsExpanded();
const alternatives=node('cloud').innerHTML,filteredCount=filtered().length;
F.cats.add('financial_crime');F.bias.add('Mixed');F.severe=true;renderCloud();
return {alternatives,filteredCount,narrowed:node('cloud').innerHTML};
""")
        rows = Markup(result["alternatives"]).with_class("term-row")
        self.assertEqual(len(rows), 12)
        self.assertEqual(result["filteredCount"], 2)
        self.assertIn('data-term="other"', result["alternatives"])
        self.assertTrue(any(a["data-term"] == "risk 0" and a["aria-pressed"] == "true" for _, a in rows))
        narrowed = Markup(result["narrowed"]).with_class("term-row")
        self.assertEqual(len(narrowed), 10)
        self.assertNotIn('data-term="other"', result["narrowed"])
        self.assertEqual(narrowed[0][1]["aria-label"], "risk 0: 1 article")

    def test_expanding_and_collapsing_preserves_active_filters(self):
        result = self.run_js("""
F.terms.add('risk 9');F.cats.add('financial_crime');F.severe=true;
renderCloud();toggleTermsExpanded();const expanded=node('cloud').innerHTML;
toggleTermsExpanded();return {expanded,collapsed:node('cloud').innerHTML,
 terms:[...F.terms],cats:[...F.cats],severe:F.severe};
""")
        self.assertIn('aria-expanded="true"', result["expanded"])
        self.assertIn('aria-expanded="false"', result["collapsed"])
        self.assertEqual(len(Markup(result["collapsed"]).with_class("term-row")), 8)
        self.assertEqual(result["terms"], ["risk 9"])
        self.assertEqual(result["cats"], ["financial_crime"])
        self.assertTrue(result["severe"])

    def test_hostile_term_is_escaped_and_handler_round_trips(self):
        term = '\"><img src=x>\'\\\n\u2028payload'
        data = fixture()
        for article in data["adverse_media"]:
            article["risk_terms"] = [{"term": term, "score": .8}]
        html = self.run_js("renderCloud();return node('cloud').innerHTML;", data)
        self.assertNotIn("<img", html)
        row = Markup(html).with_class("term-row")[0][1]
        self.assertEqual(row["data-term"], term)
        selected = self.run_js("let captured;toggleTerm=value=>captured=value;" + row["onclick"] + ";return captured;", data)
        self.assertEqual(selected, term)

    def test_coverage_is_scoped_counts_articles_once_and_states_overlap(self):
        result = self.run_js("""
renderCoverage();const all=node('catbars').innerHTML;
F.terms.add('other');renderCoverage();return {all,filtered:node('catbars').innerHTML,scope:node('scopeLabel').textContent};
""")
        counts = Markup(result["all"]).with_class("coverage-count")
        self.assertEqual(counts[0][1]["aria-label"], "2 of 3 articles")
        self.assertEqual(counts[2][1]["aria-label"], "2 of 3 articles")
        self.assertIn("width:67%", result["all"])
        self.assertIn("more than one category", result["all"])
        self.assertIn("All evidence", result["all"])
        self.assertIn("Filtered evidence", result["filtered"])
        self.assertIn("1 of 3 articles", result["filtered"])
        self.assertEqual(result["scope"], "Filtered evidence")
        self.assertIn("width:0%", result["filtered"])
        self.assertIn("width:100%", result["filtered"])

    def test_monthly_bars_have_real_dates_counts_and_single_month_state(self):
        result = self.run_js("""
renderCoverage();const all=node('timeline').innerHTML;
F.terms.add('other');renderCoverage();return {all,one:node('timeline').innerHTML};
""")
        all_markup = Markup(result["all"])
        self.assertEqual([tag for tag, _ in all_markup.with_class("volume-bar")], ["span", "span"])
        self.assertIn('height:50%', result["all"])
        self.assertIn('height:100%', result["all"])
        self.assertEqual([a["datetime"] for _, a in all_markup.with_class("volume-label")], ["2025-12", "2026-01"])
        self.assertIn("2025 - 2026", result["all"])
        self.assertIn('aria-label="January 2026: 2 articles"', result["all"])
        self.assertIn('aria-label="January 2026">Jan</time>', result["all"])
        self.assertEqual(len(Markup(result["one"]).with_class("volume-bar")), 1)
        self.assertIn('aria-label="January 2026: 1 article"', result["one"])

    def test_term_scope_states_denominator_and_excluded_term_filters(self):
        result = self.run_js("""
renderCloud();const all=node('cloud').innerHTML;
F.terms.add('other');renderCloud();return {all,filtered:node('cloud').innerHTML};
""")
        self.assertIn("Article counts across 3 articles.", result["all"])
        self.assertIn("Article counts across 3 articles; excludes term selections.", result["filtered"])

    def test_bias_disclosures_preserve_annotations_and_open_state(self):
        result = self.run_js("""
renderBias();const all=node('biasTable').innerHTML;
node('bd0').open=true;node('onlyFlagged').checked=true;renderBias();
const flagged=node('biasTable').innerHTML,open=node('bd0').open;
F.bias.add('Mixed');renderBias();const stable=node('bd0').open;
toggleDetail(0);return {all,flagged,open,stable,toggled:node('bd0').open,count:node('biasCount').textContent};
""")
        markup = Markup(result["all"])
        self.assertEqual([tag for tag, _ in markup.with_class("bias-item")], ["details"] * 3)
        self.assertEqual(sum(tag == "summary" for tag, _ in markup.elements), 3)
        self.assertNotIn("<table", result["all"])
        self.assertIn("A neutral sentence.", result["all"])
        self.assertNotIn("A neutral sentence.", result["flagged"])
        self.assertIn('<mark class="t-loaded_language"', result["flagged"])
        self.assertIn("not a factual accuracy check", result["all"])
        self.assertIn("language flags", result["count"])
        self.assertNotIn("non-factual", result["count"])
        self.assertTrue(result["open"] and result["stable"])
        self.assertFalse(result["toggled"])

    def test_article_severity_is_clamped_links_safe_and_mobile_metadata_complete(self):
        data = fixture()
        articles = []
        for severity in (8, -2, "0.5;color:red", None):
            article = deepcopy(data["adverse_media"][0])
            article.update(severity=severity, title="<img src=x>", source="<svg>Source")
            articles.append(article)
        data["adverse_media"] = articles
        html = self.run_js("renderResults();return node('resultsList').innerHTML;", data)
        self.assertNotIn("<img", html)
        self.assertNotIn("<svg", html)
        self.assertIn("&lt;img", html)
        self.assertIn('class="severity-value">1.00', html)
        self.assertIn('class="severity-value">0.00', html)
        self.assertEqual(html.count('class="severity-value">Not scored'), 2)
        self.assertNotIn("color:red", html)
        self.assertIn("data-motion-bar", html)
        markup = Markup(html)
        self.assertEqual(len(markup.with_class("article-source")), 4)
        self.assertIn("2025-12-01", html)
        self.assertIn("Objectivity", html)
        for tag, attrs in markup.elements:
            if tag == "a":
                self.assertTrue(attrs["href"].startswith("https://"))
                self.assertIn("noopener", attrs["rel"])

    def test_empty_evidence_and_undated_articles_have_explicit_states(self):
        data = fixture()
        data["adverse_media"] = []
        data["media_summary"]["total"] = 0
        result = self.run_js("renderDashboard();return ['cloud','biasTable','resultsList','catbars','timeline','breadcrumb'].map(id=>node(id).innerHTML);", data)
        self.assertIn("No risk terms", result[0])
        self.assertIn("No articles with analyzable content", result[1])
        self.assertIn('colspan="6"', result[2])
        self.assertIn("0 articles", result[3])
        self.assertIn("No dated articles", result[4])
        self.assertEqual(Markup(result[5]).text, ["All evidence"])
        self.assertNotIn("NaN", "".join(result))
        for article in data.setdefault("adverse_media", []):
            article["date"] = None
        data["adverse_media"] = [{"date": "2026-99-01"}]
        html = self.run_js("renderCoverage();return node('timeline').innerHTML;", data)
        self.assertIn("1 article with no valid month", html)

    def test_evidence_tabs_support_roving_focus_wrap_home_end_and_invalid_keys(self):
        states = self.run_js("""
const states=[];setEvidenceTab('media');states.push(tabState());
for(const [key,index] of [['ArrowRight',0],['End',1],['ArrowRight',2],['ArrowLeft',0],['Home',2]]){
 evidenceTabKey({key,target:{closest:()=>tabs[index]},preventDefault(){}});states.push(tabState());
}
setEvidenceTab('invalid');states.push(tabState());
evidenceTabKey({key:'Enter',target:tabs[0],preventDefault(){throw new Error('Unexpected preventDefault');}});
return states;
""")
        for expected, state in zip(["media", "signals", "records", "media", "records", "media", "media"], states):
            self.assertEqual(state["selected"], [expected])
            self.assertEqual(state["visible"], [expected])
            self.assertEqual(state["stops"], [expected])
        self.assertEqual(states[1]["focused"], "evidence-tab-signals")

    def test_sample_loading_errors_are_visible_without_replacing_the_report(self):
        result = self.run_js("""
let reject;requestJSON=()=>new Promise((_,r)=>reject=r);
const loading=loadDemo('failed'),during=node('evidenceStatus').textContent;
reject(new Error('Sample unavailable'));await loading;
return {during,after:node('evidenceStatus').textContent,kind:node('evidenceStatus').className,same:DATA===fixture};
""")
        self.assertEqual(result["during"], "Loading sample entity...")
        self.assertEqual(result["after"], "Sample unavailable")
        self.assertEqual(result["kind"], "status err")
        self.assertTrue(result["same"])

    def test_success_resets_disclosures_tabs_filters_and_clears_transient_status(self):
        result = self.run_js("""
renderDashboard();toggleTermsExpanded();node('bd0').open=true;
F.terms.add('other');setEvidenceTab('records');
requestJSON=async()=>fixture;await loadDemo('new');
return {status:node('evidenceStatus').textContent,terms:[...F.terms],expanded:EVIDENCE_TERMS_EXPANDED,
 open:node('bd0').open,tab:tabState(),meta:node('caseMeta').innerHTML};
""")
        self.assertEqual(result["status"], "")
        self.assertEqual(result["terms"], [])
        self.assertFalse(result["expanded"] or result["open"])
        self.assertEqual(result["tab"]["selected"], ["media"])
        self.assertIn("Sample / offline", result["meta"])

    def test_stale_sample_failure_cannot_overwrite_current_status(self):
        result = self.run_js("""
const pending=[];requestJSON=()=>new Promise((resolve,reject)=>pending.push({resolve,reject}));
const old=loadDemo('old'),current=loadDemo('current');
pending[1].resolve(fixture);await current;
pending[0].reject(new Error('Stale failure'));await old;
return {status:node('evidenceStatus').textContent,id:CURRENT_ID};
""")
        self.assertEqual(result, {"status": "", "id": "current"})


if __name__ == "__main__":
    unittest.main()
