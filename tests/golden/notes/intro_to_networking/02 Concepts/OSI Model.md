---
type: "concept"
aliases: ["Open Systems Interconnection model"]
topic: "Networking"
seen_in: ["[[Intro to Networking]]"]
open_flags: 0
card_count: 0
last_updated: 2026-10-28
---
# OSI Model

## Definition

%% recon:start definition %%
> [!info] Generated definition
> The OSI model is a conceptual framework that divides network communication into seven distinct layers. Layer 1 is Physical, Layer 2 is Data Link, Layer 3 is Network, Layer 4 is Transport, Layer 5 is Session, Layer 6 is Presentation, and Layer 7 is Application.
%% recon:end %%

## Notes

%% recon:start from-intro-to-networking %%
### From [[Intro to Networking]], 28 October 2026

- OSI splits networking into 7 layers, from Physical (1) up to Application (7).
- Layer 7 is the Application layer.
- Layer 4 is the Transport layer.
- Layer 3 is the [[Network]] layer.
- Layer 2 is the Data link layer.
- Layer 1 is the Physical layer.

**Easy to get wrong**

- It is unclear where [[TLS]] sits, possibly in the Session or Presentation layer.
%% recon:end %%

## Related

%% recon:start related %%
- [[TCP]]
- [[UDP]]
- [[HTTP]]
- [[IP]]
- [[Ethernet]]
%% recon:end %%
