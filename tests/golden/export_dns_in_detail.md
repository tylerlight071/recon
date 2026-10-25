# DNS in Detail

TryHackMe · Pre Security · Network Fundamentals
Finished 25 October 2026 · 1 hour 12 minutes

## Task 1: Record types

**Key idea**
Each record type answers a different question.

**Command**
```sh
dig example.com MX  # who handles mail
```

**Table**
| Type | Holds |
| --- | --- |
| A | IPv4 address |
| TXT | free text \| notes |

**Question**
Why can't CNAME share a name?

**Room question**
Which record holds a mail server?

> [!question]- Answer
> MX

## Task 2

*Skipped.*

## Task 3: Hashes

**Key idea**
md5 of hello: 5d41402abc4b2a76b9719d911017c592 (kept)

**Key idea**
\# not a heading
\> not a quote
\---
\%\% not hidden \%\%
