### Removed

- The `forced_choice_leakage` scanner. A question that offers its answer as one of two options ("Is it an MRI or a CT scan?") is an ordinary binary question: a model that pattern-matches still has to choose between the options. On a sweep of every Inspect Evals eval it reported 1,614 findings, 1,333 of them on DROP's reading-comprehension questions ("Which happened first, X or Y?", answered from a passage), and none worth acting on. `binary_question_ratio` still reports datasets dominated by binary questions. `--scanners forced_choice_leakage` is now an unknown scanner.
