"""Saved (hand-constructed, realistically shaped) Nairaland search-results HTML.

Mirrors the real DOM structure confirmed against a live
``nairaland.com/search?q=...&board=0&p=N`` response during Milestone 7's
build: each result is a ``<td class="bold l pu">`` row (title/section/
author/permalink/timestamp) immediately followed by a
``<td id="pb{post_id}">`` row (the post body).
"""

SAMPLE_SEARCH_PAGE_HTML = """
<html><body><table>
<tr>
<td class="bold l pu">
  <a name="140122189"></a><a name="msg140122189"></a><a name="8715056.1"></a>
  <img src="/icons/xx.gif">
  <a href="/crime">Crime</a> &#8250;
  <a href="/8715056/me-recover-money-riglance-been#140122189">Re: Help Me Recover My Money From Riglance</a>
  by <a class="user" href="/maxinvile">maxinvile</a>:
  <span class="s"><b>6:51pm</b> On <b>Jul 23</b></span>
</td>
</tr>
<tr>
<td id="pb140122189" class="l w pd">
  <div class="narrow">Wema Bank fraud alert - my transfer failed and support never responded to my BVN complaint.</div>
</td>
</tr>
<tr>
<td class="bold l pu">
  <a name="140122128"></a><a name="msg140122128"></a><a name="8715056.0"></a>
  <img src="/icons/xx.gif">
  <a href="/crime">Crime</a> &#8250;
  <a href="/8715056/me-recover-money-riglance-been#140122128">Help Me Recover My Money From Riglance</a>
  by <a class="user" href="/chukan">chukan</a>:
  <span class="s"><b>6:43pm</b> On <b>Jul 23</b></span>
</td>
</tr>
<tr>
<td id="pb140122128" class="l w pd">
  <div class="narrow">Dear Nairaland Members, I am seeking advice regarding a fraud case with my Wema bank account.</div>
</td>
</tr>
</table></body></html>
"""

EMPTY_SEARCH_PAGE_HTML = """
<html><body><table>
<tr><td class="w">No matching results.</td></tr>
</table></body></html>
"""
