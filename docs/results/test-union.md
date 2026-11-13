# test split, union: 102 contracts

| field | correct | wrong | missed | false alarm | true empty | flagged | unscorable | accuracy where gold has a value |
|---|---|---|---|---|---|---|---|---|
| expiration | 37 | 7 | 15 | 10 | 27 | 0 | 6 | 62.7% (37/59) |
| renewal | 20 | 0 | 3 | 4 | 74 | 0 | 1 | 87.0% (20/23) |
| notice | 12 | 0 | 1 | 9 | 80 | 0 | 0 | 92.3% (12/13) |
| deadline | 4 | 3 | 0 | 0 | 0 | 3 | 0 | 40.0% (4/10) |
