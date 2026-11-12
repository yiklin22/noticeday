# test split, rules: 102 contracts

| field | correct | wrong | missed | false alarm | true empty | flagged | unscorable | accuracy where gold has a value |
|---|---|---|---|---|---|---|---|---|
| expiration | 26 | 9 | 24 | 4 | 33 | 0 | 6 | 44.1% (26/59) |
| renewal | 17 | 0 | 6 | 3 | 75 | 0 | 1 | 73.9% (17/23) |
| notice | 11 | 0 | 2 | 2 | 87 | 0 | 0 | 84.6% (11/13) |
| deadline | 2 | 2 | 0 | 0 | 0 | 6 | 0 | 20.0% (2/10) |
