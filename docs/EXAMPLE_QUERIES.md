# Suggested queries for the judges

Try each query with the DEMO001 sample user unless otherwise specified.

**Knowledge only:** 'How do I reset my password?' Should search KB001 and not request an asset.

**Clear request:** 'I need Microsoft Visio installed.' Should classify Service Request and offering REQ011, and avoid looking for a laptop asset.

**Clear incident:** 'My Dell laptop is not turning on.' Should find KB002, and if unresolved classify Incident and offering INC001.

**Multiple asset clarification:** 'My Dell computer is broken.' DEMO001 has a Dell desktop and two Dell laptops. After 'laptop', it still must ask which model. It should not pick randomly.

**Access request:** 'Please give me SAP access.' Should propose a service request for SAP Access.

**Direct agent:** 'Connect me with an agent about my broken laptop.' Should prepare the issue classification, not insist on finding an article first.

**Out of scope:** 'Who won the cricket match yesterday?' Should not create a ticket.

**Unsupported policy:** 'What is our maternity leave policy?' No corresponding sample article exists, so it must not fabricate a policy answer.

**Multiple intents:** 'My laptop is broken and I need a replacement.' Should recognise possible Incident plus separate Service Request and ask which action to take or whether both are desired.

Every expected behaviour above is a test specification, not a validated Clocked result. Real API behaviour must be measured after integration.
