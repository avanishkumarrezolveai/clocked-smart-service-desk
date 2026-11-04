# Decision rules for the future application

1. Accept typed, pasted or spoken text. Voice transcription is user correctable.
2. Identify scope, user action and intent. Direct ticket or Live Chat requests are allowed to bypass knowledge assistance.
3. For informational or troubleshooting questions, search local knowledge first. Verify the proposed answer against cited text before presenting it as supported.
4. When the user needs escalation, classify Incident vs Service Request using Clocked Decide.
5. Retrieve a shortlist of catalog offerings, ask Clocked to select among them, then enforce matching ticket type.
6. Only categories permitted in `offering_mappings.csv` are valid. The subcategory must belong to its selected parent category.
7. Determine whether a specific asset is needed for this workflow. Avoid asking irrelevant asset questions.
8. If multiple assets belonging to that demo user match, ask the shortest useful disambiguating question (brand, device type, model, location or device label). Never guess a serial number or device ID.
9. Check mandatory/conditional fields in `offering_fields.csv` and ask only for missing details.
10. Show the ticket type, offering, category, subcategory, affected asset if applicable, and issue summary before user confirmation.
11. Offer simulated ticket creation or simulated Live Chat handoff, preparing the same structured context for both.
12. Maintain conversation state so a user can say 'it is the other Dell laptop' and be understood.
13. If out of scope or uncertain, do not fabricate ticket IDs, knowledge citations or Clocked results.
14. Display actual Clocked endpoint, timing, alternatives and returned probability (when available) in a separate judge trace. Keep private tokens invisible.
15. The same app should work against synthetic files without production systems. Provide a distinctly marked demonstration mode when the Clocked API key is absent.
