---
type: "raw"
platform: "TryHackMe"
path: "Foundations"
module: "Computer Basics"
room: "Number Systems"
captured_on: 2026-10-28
time_spent: 31
---
# Number Systems (raw notes)

## Task 1: Why bases matter

**Key idea**
Computers only store bits, so we write numbers in base 2 or base 16 to see what's actually in memory.

**Confused by**
Why do people bother with hex instead of just reading the binary?

## Task 2: Binary

**Key idea**
Each binary place is a power of 2: 1, 2, 4, 8, 16 going right to left.

**Key idea**
1101 in binary is 11 in decimal.

**Table**
| Binary | Decimal |
| --- | --- |
| 0001 | 1 |
| 0010 | 2 |
| 0100 | 4 |
| 1000 | 8 |

## Task 3: Hexadecimal

**Key idea**
Hex uses 0-9 then A-F, so one hex digit is exactly 4 bits.

**Key idea**
0x2F is 46 in decimal.

**Table**
| Hex | Decimal | Binary |
| --- | --- | --- |
| A | 10 | 1010 |
| F | 15 | 1111 |
| 10 | 16 | 10000 |

## Task 4: Converting between bases

**Key idea**
Binary to hex: split the bits into groups of 4 from the right and swap each group for one hex digit.

**Key idea**
0xFF is 255, the biggest number one byte can hold.

**Question**
Is there a quick way to do decimal to hex in my head?

**Room question**
What is 0b1010 in decimal?

> [!question]- Answer
> 10

## Task 5: Wrap-up

*Skipped.*
