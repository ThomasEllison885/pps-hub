# Ask PPS — Team capture question bank

**Use:** 30-minute all-hands answering on Hub dashboard (Help document PPS).  
**Updated:** 2026-07-27

## What people see on the dashboard

| Who | What they see |
|-----|----------------|
| **Everyone (logged in)** | A card: **Help document PPS** with one prompt question, text box, **Submit answer**, **Skip for now**, and link to full Ask PPS. Answers save **under their name**. |
| **PSCs (consultants)** | Same card; queue **weighted** toward consultant / training / sales questions (PM questions still appear less often). Order is **randomized per person**. |
| **PMs** | Same card; queue **weighted** toward production / Trade Partner / PPM / callback questions. Randomized. |
| **Stephanie / Thomas / others** | Same card; **equal random** across the full open bank they can answer. |
| **Curators only (Thomas, Tony, Trey)** | Header link **Ask PPS** with open-gap badge; `/admin/ask-pps` for review of pending answers. |

If the bank was empty, the next dashboard load **auto-seeds** prompts from identified training/ops gaps.

---

## Full question list (sources)

### A. PSC Training gaps (`[TO DOCUMENT]` — field_role as noted)

1. **[consultant]** Criteria for when a PSC is cleared for independent client-facing work  
2. **[consultant]** Naming conventions for properties, contacts, and deals (Monday.com)  
3. **[pm]** Callback and warranty handoff at close-out  
4. **[consultant]** Standard site-visit checklist by trade  
5. **[consultant]** Central reference for common unit costs by trade  
6. **[consultant]** After-hours and urgent site escalation path  
7. **[pm]** How we find and recruit new Trade Partners  
8. **[pm]** Vetting criteria — insurance, references, trade quality, responsiveness  
9. **[pm]** QC expectations and payment triggers  
10. **[pm]** Preferred Trade Partner reference — trade, contact, specialty  
11. **[consultant]** Communication examples library by phase  
12. **[pm]** Standard callback intake and close-out checklist  
13. **[consultant]** Common mistake: promising schedule/scope production has not confirmed  
14. **[consultant]** Common mistake: under-documenting site visits  
15. **[consultant]** Common mistake: sending proposals cold without a review conversation  
16. **[consultant]** Common mistake: Monday.com hygiene slip in first 30 days  
17. **[consultant]** Common mistake: bypassing PM on site or client issues  
18. **[consultant]** Common mistake: generic contractor language instead of PPS voice  

### B. PSC feedback themes (Rachel / curriculum)

19. **[consultant]** How is a mentor consultant chosen for partner-project onboarding, and what makes a good partner project?  
20. **[consultant]** How does responsibility shift observe → participate → lead? Real example.  
21. **[consultant]** What should a post-project debrief cover — and who runs it?  
22. **[consultant]** Standard client communication touchpoints by project phase  
23. **[consultant]** Schedule delay conversation with a property manager — what do you say first?  
24. **[consultant]** What do you always capture on a site visit before scoping?  
25. **[consultant]** Pricing support, callbacks, change orders, concealed conditions — who owns vs who is looped in?  
26. **[consultant]** What must a PSC gather so a PM can build an accurate production price?  
27. **[pm]** Go-to Trade Partners by trade, and how you choose?  
28. **[pm]** Callback/warranty intake walkthrough  
29. **[consultant]** Signs a new PSC is ready for independent client-facing work  

### C. Knowledge audit (ops staples)

30. **[pm]** How does PPM actually run — who attends, agenda, what must be confirmed before mobilization?  
31. **[pm]** Change order from discovery to approval  
32. **[pm]** Punch list and close-out handoff  
33. **[consultant]** Proposal review before it goes to a client  
34. **[consultant]** Roofing/trade warranty language to clients  

### D. Thin-category templates (if KB is sparse)

35. **[pm]** Typical mobilization — PPM through first day on site  
36. **[consultant]** First contact through awarded proposal — real steps today  
37. **[any]** One operations habit or handoff that keeps jobs from slipping  
38. **[any]** For your main trade — what do new PMs or consultants get wrong most often?  

Plus any **open Q&A gaps** already in the database from people asking Ask PPS questions that could not be answered.

---

## Attribution (who answered)

Every submission is stored as a **pending knowledge entry** with:

- **Title:** `{Display Name}: {question…}`  
- **Body header:** `Submitted by: Name · Title · hub:user_key · email` + timestamp  
- **author_key** on the row for admin filters  
- Admin **Pending** list shows `author_display · category`

You review at **Admin → Ask PPS → Pending**.

---

## How to run the 30-minute session

1. Deploy this Hub build.  
2. Tell everyone: open **PPS Hub dashboard** (or Add to Home Screen), log in, scroll to **Help document PPS**.  
3. Goal: answer as many as you can in 30 minutes; **Skip** if you truly don’t know.  
4. Afterward: open **Admin → Ask PPS → Pending** and approve/edit the best answers into the knowledge base.

**PSCs** will mostly see sales/training items first. **PMs** will mostly see production/Trade Partner items first. Same bank — different shuffle.
