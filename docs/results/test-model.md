# test split, model: 102 contracts

| field | correct | wrong | missed | false alarm | true empty | flagged | unscorable | accuracy where gold has a value |
|---|---|---|---|---|---|---|---|---|
| expiration | 26 | 5 | 28 | 9 | 28 | 0 | 6 | 44.1% (26/59) |
| renewal | 19 | 0 | 4 | 2 | 76 | 0 | 1 | 82.6% (19/23) |
| notice | 11 | 0 | 2 | 9 | 80 | 0 | 0 | 84.6% (11/13) |
| deadline | 1 | 3 | 0 | 0 | 0 | 6 | 0 | 10.0% (1/10) |
