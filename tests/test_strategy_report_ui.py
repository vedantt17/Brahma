"""Offline tests for report content, escaping, sorting, and accessible tabs."""

from collections import Counter
from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from app.strategy.samples import SAMPLES


ROOT = Path(__file__).resolve().parents[1]


class ReportMarkup(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.text = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


@unittest.skipUnless(shutil.which("node"), "Node is required for renderer tests")
class StrategyReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = list(SAMPLES.values())
        live = deepcopy(cls.samples[0])
        live["generated_by"] = "live model"
        live["sample"] = False
        live["evidence_audit"]["verification_mode"] = "model_self_assessment"
        hostile = {
            "verdict": {"chair_summary": '<img src=x onerror="alert(1)">'},
            "stakes": "<script>alert(1)</script>",
            "conditions": ['<a href="javascript:alert(1)">link</a>'],
            "seats": [{"seat": "<iframe>", "role": "<script>", "staffed": True,
                       "headline": "<img>", "risks": ["<svg onload=alert(1)>"],
                       "risk_score": "90; color:red", "conviction": 999}],
            "board_vote": [{"member": "<img>", "vote": "<script>", "rationale": "<svg>"}],
            "attacks": [{"target_seat": "<img>", "claim_attacked": "<script>", "why_it_breaks": "<iframe>"}],
            "evidence_audit": {"audited_claims": [{"seat": "<img>", "claim": "<script>", "reason": "<iframe>", "verdict": "<svg>"}]},
        }
        harness = r"""
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const stop=new Error('stop startup');
const context=vm.createContext({URL,window:{addEventListener(){}},
  document:{getElementById(){throw stop;}}});
try{vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);}
catch(error){if(error!==stop)throw error;}
const render=(data,origin='sample')=>{
  context.fixture=data;context.origin=origin;
  return vm.runInContext('STRAT=fixture;STRAT_ORIGIN=origin;renderAnalysisReport()',context);
};
const samples=input.samples.map(s=>render(s));
const live=render(input.live,'live'),hostile=render(input.hostile),empty=render({});
render(input.samples[0]);
const sorted={};
let lastHTML='';
context.document.getElementById=id=>({set innerHTML(html){lastHTML=html;}});
for(const value of ['risk_score:desc','risk_score:asc','conviction:desc','seat:asc']){
  context.sortValue=value;vm.runInContext('sortSeats(sortValue)',context);sorted[value]=lastHTML;
}
const keys=['overview','team','evidence','challenges'];
let focused='';
const tabs=keys.map(key=>({dataset:{reportTab:key},attrs:{},tabIndex:-1,
  setAttribute(k,v){this.attrs[k]=v;},focus(){focused=key;}}));
const panels=keys.map(key=>({dataset:{reportPanel:key},hidden:true}));
context.document.getElementById=id=>({querySelectorAll(selector){return selector==='[role="tab"]'?tabs:panels;}});
const states=[];
function state(){states.push({selected:tabs.filter(t=>t.attrs['aria-selected']==='true').map(t=>t.dataset.reportTab),
  visible:panels.filter(p=>!p.hidden).map(p=>p.dataset.reportPanel),
  stops:tabs.filter(t=>t.tabIndex===0).map(t=>t.dataset.reportTab),focused});}
vm.runInContext("setReportTab('overview')",context);state();
for(const [key,current] of [['ArrowRight','overview'],['End','team'],['ArrowRight','challenges'],['ArrowLeft','overview'],['Home','challenges']]){
  context.event={key,target:tabs.find(t=>t.dataset.reportTab===current),preventDefault(){}};
  vm.runInContext('reportTabKey(event)',context);state();
}
vm.runInContext("setReportTab('invalid')",context);state();
process.stdout.write(JSON.stringify({samples,live,hostile,empty,sorted,states}));
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", harness, str(ROOT / "static" / "app.js")],
            input=json.dumps({"samples": cls.samples, "live": live, "hostile": hostile}),
            capture_output=True, text=True, encoding="utf-8", timeout=15, check=True,
        )
        cls.rendered = json.loads(result.stdout)

    def test_every_existing_report_detail_is_preserved(self):
        for source, html in zip(self.samples, self.rendered["samples"]):
            text = " ".join(ReportMarkup(html).text)
            expected = [source["stakes"], source["verdict"]["chair_summary"],
                        *source.get("success_criteria", []), *source.get("conditions", [])]
            expected += [source[k] for k in ("kill_shot", "would_change_mind") if source.get(k)]
            for member in source.get("board_vote", []):
                expected.extend(member[k] for k in ("member", "vote", "rationale"))
            for seat in source.get("seats", []):
                expected.extend([seat["seat"], seat.get("role", "")])
                if seat["staffed"]:
                    expected.extend([seat.get("headline", ""), *seat.get("risks", [])])
                else:
                    expected.append(seat.get("bench_reason", ""))
            for attack in source.get("attacks", []):
                expected.extend(attack[k] for k in ("target_seat", "claim_attacked", "why_it_breaks"))
            audit = source.get("evidence_audit", {})
            expected.append(audit.get("integrity_note", ""))
            for claim in audit.get("audited_claims", []):
                expected.extend(claim[k] for k in ("seat", "claim", "reason"))
            for detail in expected:
                with self.subTest(sample=source["id"], detail=detail):
                    self.assertIn(detail, text)

    def test_tab_relationships_are_unique_and_overview_is_default(self):
        for html in self.rendered["samples"]:
            markup = ReportMarkup(html)
            ids = [attrs["id"] for _, attrs in markup.elements if "id" in attrs]
            self.assertTrue(all(count == 1 for count in Counter(ids).values()))
            tabs = [attrs for _, attrs in markup.elements if attrs.get("role") == "tab"]
            panels = [attrs for _, attrs in markup.elements if attrs.get("role") == "tabpanel"]
            self.assertEqual(len(tabs), 4)
            self.assertEqual(len(panels), 4)
            for tab, panel in zip(tabs, panels):
                self.assertEqual(tab["aria-controls"], panel["id"])
                self.assertEqual(panel["aria-labelledby"], tab["id"])
                self.assertEqual("hidden" not in panel, tab["aria-selected"] == "true")
            self.assertEqual(tabs[0]["aria-selected"], "true")

    def test_keyboard_navigation_has_one_panel_and_one_tab_stop(self):
        for expected, state in zip(
            ["overview", "team", "challenges", "overview", "challenges", "overview", "overview"],
            self.rendered["states"],
        ):
            self.assertEqual(state["visible"], [expected])
            self.assertEqual(state["selected"], [expected])
            self.assertEqual(state["stops"], [expected])

    def test_sorting_changes_only_specialist_list_and_keeps_benched_last(self):
        for sort, html in self.rendered["sorted"].items():
            seats = self.samples[0]["seats"]
            key, direction = sort.split(":")
            expected = sorted((s for s in seats if s["staffed"]),
                              key=lambda s: s[key], reverse=direction == "desc")
            expected += [s for s in seats if not s["staffed"]]
            positions = [html.index(f"<h4>{s['seat']}</h4>") for s in expected]
            self.assertEqual(positions, sorted(positions))
            self.assertNotIn('role="tab"', html)

    def test_audit_keeps_honest_provenance_for_sample_and_live(self):
        for mode in ("samples", "live"):
            html = self.rendered[mode][0] if mode == "samples" else self.rendered[mode]
            self.assertIn("Not independently verified", html)
            self.assertIn("ratings are not evidence of retrieved or verified citations", html)
            self.assertIn("Sample-rated verified" if mode == "samples" else "Model-rated verified", html)

    def test_untrusted_text_is_escaped_and_score_widths_are_clamped(self):
        html = self.rendered["hostile"]
        tags = {tag for tag, _ in ReportMarkup(html).elements}
        self.assertFalse(tags.intersection({"img", "script", "iframe", "a", "svg"}))
        self.assertIn("&lt;img", html)
        self.assertIn('style="width:100%"', html)
        self.assertIn('style="width:0%"', html)

    def test_missing_optional_sections_have_explicit_empty_states(self):
        html = self.rendered["empty"]
        for message in ("No success criteria recorded.", "No conditions recorded.",
                        "No board votes recorded.", "No specialist assessments recorded.",
                        "No evidence audit recorded.", "No challenges recorded."):
            self.assertIn(message, html)


if __name__ == "__main__":
    unittest.main()
