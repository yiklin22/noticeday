# test split, union: 102 contracts

| field | correct | wrong | missed | false alarm | true empty | flagged | unscorable | accuracy where gold has a value |
|---|---|---|---|---|---|---|---|---|
| expiration | 38 | 7 | 14 | 10 | 27 | 0 | 6 | 64.4% (38/59) |
| renewal | 20 | 0 | 3 | 5 | 73 | 0 | 1 | 87.0% (20/23) |
| notice | 12 | 0 | 1 | 9 | 80 | 0 | 0 | 92.3% (12/13) |
| deadline | 4 | 3 | 0 | 0 | 0 | 3 | 0 | 40.0% (4/10) |
