# 📓Guide to understanding how rules work in the Tau test-net

## Background

The Tau test-net allows for transactions between two addresses just like a conventional blockchain. However, what sets it apart is the unique ability to introduce rules. These rules govern how the test-net processes transactions.

These rules can be modified block-by-block, creating a dynamic blockchain with governance that is flexible over time.

For example, in block #10, there is a collection of rules that allows anyone to send any amount of Agoras, provided it does not exceed the wallet balance. However, Bob decides that for block #11, he wants to introduce a new rule that will restrict future transactions to exactly 66 Agoras—no more, no less.

Bob can perform a transaction introducing this new rule. If accepted, block #11 will now contain a new condition: to process block #12, Bob and everyone else can only send 66 Agoras; any other amount is rejected by Tau.

How is this implemented? Thanks to Tau, each block is verified according to the current rules. Tau verifies that the new transaction complies with all rules and decides whether the transaction is valid or not.

There is a collection of basic rules that govern the test-net at its inception. These are:

- **Rule to detect insufficient funds**
- **Rule to verify that the sending address is different from the receiving one**
- **Rule to verify if the amount to send is 0**
- **Rule to detect invalid inputs**

## Example

### How is a rule defined? The rule to detect insufficient funds

Logic: If the value to transfer is greater than the balance, Tau must respond false (0) and the transaction must be rejected. Otherwise, Tau must respond true (1) and the transaction be accepted..

In this case, a ternary operator is used. The syntax in the Tau language is defined as follows: *Note: Tau-Lang is in alpha phase; syntax may change in the future*

>**(** Condition **?** Action_if_true **:** Action_if_false **)**

The rule discussed here, written in Tau language as a ternary operator, is:

>always **(**(i1\[t\] : bv\[64\] > i2\[t\]) **?** o2\[t\] = { #b0 }:bv\[1\] **:** o2\[t\] = { #b1 }:bv\[1\]**)**.

*Translation: Always, if i1\[t\] is greater than i2\[t\] **:** If true, respond 1, otherwise 0.*

What does each input and output of this rule mean?

Input Streams: Input values to Tau.

> **i1\[t\]: Amount to send (64-bit bitvector)**

> **i2\[t\]: Balance of the sender (64-bit bitvector)**

Output Streams: Values that Tau responds with.

> **o2\[t\]: validation (0 or 1). If 1, the rule is valid and the transaction is accepted, if 0, it is rejected.**

---

**In General:**

| **Stream** | **Type** | **Name** | **Description** |
| --- | --- | --- | --- |
| **i0\[t\]** | tau | **Rule Proposal** | Used for submitting new Tau code to update the blockchain's rules (via Pointwise Revision). |
| **i1\[t\]** | bv\[64\] | **Transfer Amount** | The quantity of coins the sender _wants_ to transfer in the current transaction. |
| **i2\[t\]** | bv\[64\] | **Sender Balance** | The current wallet balance of the sender _before_ the transaction is processed. |
| **i3\[t\]** | bv\[64\] | **Source Address** | The unique ID (address) of the person sending the coins. |
| **i4\[t\]** | bv\[64\] | **Dest. Address** | The unique ID (address) of the person receiving the coins. |

| **Stream** | **Type** | **Role** | **What it means** |
| --- | --- | --- | --- |
| **o1\[t\]** | **Data** | **The Final Amount** | "We are moving **X** coins." |
| **o2\[t\]** | **Flag** | **Funds Check** | "Does the sender have enough money?" (1 = Yes, 0 = No) |
| **o3\[t\]** | **Flag** | **Address Check** | "Are Sender and Receiver different people?" (1 = Yes, 0 = No) |
| **o4\[t\]** | **Flag** | **Logic Check** | "Is the amount valid (e.g., not zero)?" (1 = Yes, 0 = No) |

---
