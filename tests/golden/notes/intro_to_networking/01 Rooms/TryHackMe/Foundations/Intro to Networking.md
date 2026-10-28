---
type: "room"
platform: "TryHackMe"
path: "Foundations"
module: "Computer Basics"
room: "Intro to Networking"
date_done: 2026-10-28
time_spent: 40
concepts: ["[[Network]]", "[[OSI Model]]", "[[TCP]]", "[[UDP]]", "[[DNS]]", "[[HTTP]]", "[[HTTPS]]", "[[SSH]]", "[[FTP]]", "[[IP]]", "[[Ethernet]]", "[[TLS]]"]
tools: []
open_flags: 0
raw_notes: "[[Intro to Networking (raw notes)]]"
---
# Intro to Networking

## Summary

%% recon:start summary %%
- This room introduced the basic concept of a computer [[Network|network]] and the internet as interconnected networks.
- It explained the [[OSI Model|OSI model]]'s seven layers and where specific protocols like [[HTTP]] and [[TCP]] fit.
- The notes covered the differences between connection-oriented [[TCP]] and connectionless [[UDP]].
- Common ports for services like [[HTTP]], [[HTTPS]], [[DNS]], [[SSH]], and [[FTP]] were listed with their default numbers.
- A question was raised about the location of [[TLS]] within the [[OSI Model|OSI model]].
%% recon:end %%

## Tasks

%% recon:start tasks %%
### Task 1: What a network is

- A [[Network|network]] consists of devices that can send data to each other.
- The internet is formed by joining many networks together.

### Task 2: The OSI model

- The [[OSI Model|OSI model]] divides networking into seven layers.
- Layer 7 is the Application layer, used by [[HTTP]].
- Layer 4 is the Transport layer, using [[TCP]] and [[UDP]].
- Layer 3 is the [[Network]] layer, used by [[IP]].
- Layer 2 is the Data link layer, using [[Ethernet]].
- Layer 1 is the Physical layer, involving cables and Wi-Fi radio.

### Task 3: TCP and UDP

- [[TCP]] establishes a connection using a three-way handshake with SYN, SYN-ACK, and ACK packets.
- [[TCP]] resends any data that gets lost during transmission.
- [[UDP]] sends packets without a handshake.
- [[UDP]] is quicker because it lacks a handshake.
- [[UDP]] does not guarantee that packets will arrive.

### Task 4: Common ports

- Port 80 is used for [[HTTP]].
- Port 443 is used for [[HTTPS]].
- Port 53 is used for [[DNS]].
- [[SSH]] runs on port 23.
- [[FTP]] uses port 21 for its control connection.

**Room question:** Which port does HTTPS use by default?

> [!question]- Answer
> 443
%% recon:end %%

## Tables and diagrams

%% recon:start tables %%
**Task 2: The OSI model**

| Layer | Name | Example |
| --- | --- | --- |
| 7 | Application | HTTP |
| 4 | Transport | TCP, UDP |
| 3 | Network | IP |
| 2 | Data link | Ethernet |
| 1 | Physical | cables, Wi-Fi radio |

**Task 4: Common ports**

| Port | Service |
| --- | --- |
| 80 | HTTP |
| 443 | HTTPS |
| 53 | DNS |
%% recon:end %%

## Open questions

%% recon:start questions %%
**Why does DNS mostly use UDP?**

> [!note]- Suggested answer (generated)
> DNS mostly uses UDP because it is faster and the data packets are small enough that reliability can be handled at higher layers or via retries. Speed is prioritized for lookups.
%% recon:end %%

## Source notes

%% recon:start source %%
Your notes as you wrote them: [[Intro to Networking (raw notes)]]
%% recon:end %%
