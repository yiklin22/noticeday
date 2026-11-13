# test split, rules: start dates (one run)

Run once in the 13 Nov 2026 session on the extractor at commit `cca2f0c`
(the code the README's test table describes), with a scratch script that
scores the same way as `scripts/score_start_dates.py`: gold is CUAD's
effective date, or the agreement date when the effective-date field is
empty; partial dates are not scored. The scorer printed this; it is copied
here unchanged because the script did not write a results file:

```
{'nogold': 6, 'wrong': 14, 'correct': 65, 'unscorable': 9, 'missed': 8} scored 87
```

| correct | wrong | not found | not scored (no gold / partial date) |
|---|---|---|---|
| 65 | 14 | 8 | 15 (6 / 9) |

Not re-run after the review fixes, to keep to one test run.
