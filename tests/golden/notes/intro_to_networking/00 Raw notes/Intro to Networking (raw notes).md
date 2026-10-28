---
type: "raw"
platform: "TryHackMe"
path: "Foundations"
module: "Computer Basics"
room: "Intro to Networking"
captured_on: 2026-10-28
time_spent: 40
---
# Intro to Networking (raw notes)

## Task 1: What a network is

**Key idea**
A network is just devices that can send data to each other. The internet is loads of networks joined together.

## Task 2: The OSI model

**Key idea**
OSI splits networking into 7 layers, from Physical (1) up to Application (7).

**Table**
| Layer | Name | Example |
| --- | --- | --- |
| 7 | Application | HTTP |
| 4 | Transport | TCP, UDP |
| 3 | Network | IP |
| 2 | Data link | Ethernet |
| 1 | Physical | cables, Wi-Fi radio |

**Confused by**
Where does TLS actually sit? Session layer or presentation?

## Task 3: TCP and UDP

**Key idea**
TCP opens a connection with a three-way handshake (SYN, SYN-ACK, ACK) and resends anything that gets lost.

**Key idea**
UDP just sends packets with no handshake, so it's quicker but nothing is guaranteed to arrive.

**Question**
Why does DNS mostly use UDP?

## Task 4: Common ports

**Table**
| Port | Service |
| --- | --- |
| 80 | HTTP |
| 443 | HTTPS |
| 53 | DNS |

**Key idea**
SSH runs on port 23.

**Key idea**
FTP uses port 21 for its control connection.

**Room question**
Which port does HTTPS use by default?

> [!question]- Answer
> 443
