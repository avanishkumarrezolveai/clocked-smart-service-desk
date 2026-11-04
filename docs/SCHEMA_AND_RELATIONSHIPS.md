# Schema and relationships

* `users.user_id` is referenced by `assets.user_id`. A user can have zero, one or many assets.
* `ticket_types.ticket_type_id` is referenced by `offerings.ticket_type_id` and `categories.ticket_type_id`.
* `offerings.csv` is the unified catalog. `service_offerings.csv` and `incident_offerings.csv` are the two convenient subsets. Do not import all three into the same database as independent records.
* `subcategories.category_id` must match `categories.category_id`.
* `offering_mappings.csv` is the source of allowed offering/category/subcategory triples. The category ticket type must match the offering ticket type.
* `offering_mappings.is_default` indicates the recommended starting classification for that offering. This is a catalog default, not an API prediction.
* `offering_fields.csv` describes questions the application may need to ask before a simulated ticket can be created.
* `knowledge_manifest.path` gives the relative location of a real file under this project folder.
* `live_chat_queues` refers to demonstration queues only. These are never connected to actual chat servers.
* `modules.csv` declares the support capabilities and distinguishes voice input from core workflows.

## Runtime behavior at scale

Use a candidate retrieval step over `offerings.csv`, then ask Clocked Decide to choose between relevant candidates. Filter categories using `offering_mappings.csv`, then choose a category and subcategory from the allowed pairs. Check all returned IDs against the dataset before continuing. Do not provide hundreds of unrelated candidate labels in every Clocked call.

## Important asset rule

Manufacturer is a clarification clue, not necessarily a unique identifier. For DEMO001, both 'Dell' and 'Laptop' still match two devices. Ask the model or another descriptive question. Device serial number and hostname are last resorts.

## What is not included

No runnable website, Clocked key, API token, model invocation results, real ticket, employee data, production connection or real chat session is included in this pack.
