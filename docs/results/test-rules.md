# test split, rules: 102 contracts

| field | correct | wrong | missed | false alarm | true empty | flagged | unscorable | accuracy where gold has a value |
|---|---|---|---|---|---|---|---|---|
| expiration | 27 | 7 | 25 | 4 | 33 | 0 | 6 | 45.8% (27/59) |
| renewal | 17 | 0 | 6 | 3 | 75 | 0 | 1 | 73.9% (17/23) |
| notice | 11 | 0 | 2 | 2 | 87 | 0 | 0 | 84.6% (11/13) |
| deadline | 3 | 2 | 0 | 0 | 0 | 5 | 0 | 30.0% (3/10) |
