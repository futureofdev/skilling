---
title: Find and Read
phase: 1
lesson: 2
duration_minutes: 15
prerequisites: ["1.1"]
skills_unlocked: [file-wrangler]
objectives:
  - id: why-plain-text-wins
    kind: knowledge
    text: Explain why plain-text files are the easiest kind to search, compare, and version
    about: [1]
  - id: find-files-by-name-and-content
    kind: practice
    text: Locate a file by its name, and a line inside a file by its content
    verify: >
      The learner located a file by name and found a line inside a file by its content
      using search commands, rather than opening files one by one
    about: [2, 3]
  - id: keep-a-tidy-tree
    kind: practice
    text: Keep a working directory tidy enough that a stranger could find things in it
sections:
  key_terms:
    status: none
    intent: >
      Each command's name is close to its own definition here — a separate glossary would
      only restate the concept.
  exercise: present
  next_up: present
---

## The Concept

A directory full of files is only useful if you can get things back out of it. The shell
gives you two different questions to ask, and a command for each:

**"Where is the file called…?"** — `find` searches *names*:

```bash
find . -name "plan.txt"       # every file named plan.txt, from here down
find . -name "*.txt"          # every .txt file, however deep
```

**"Which file contains…?"** — `grep` searches *contents*:

```bash
grep harbor notes.txt         # lines containing "harbor" in one file
grep -r harbor .              # the same, across every file from here down
```

And for simply reading, `cat notes.txt` prints a whole file into the terminal, while
`head notes.txt` shows just the beginning — enough to check you have the right one.

All of this works because the files are **plain text**. A plain-text file has no lock-in
and no secrets: any editor can open it, `grep` can search it, `diff` can compare two
versions of it, and — as the next phase shows — git can track every change to it. The
formats that fight you (proprietary documents, exports that need one specific app) are
precisely the ones these tools cannot see inside. When you have a choice, choose text.

## Hands-On Exercise

Work inside the `practice` directory from the previous exercise (rebuild it if it's gone —
that's the point of knowing the commands).

1. Put some words into your files so there is something to find:
   `echo "meet at the harbor at noon" >> notes.txt` and
   `echo "paint the fence" >> done/plan.txt`.
2. `cat notes.txt` — read a file without opening an editor.
3. `find . -name "plan.txt"` — locate a file by name, wherever it sits.
4. `grep -r harbor .` — find which file mentions the harbor, without knowing its name.
5. Now prove the search earned its keep: `grep -r fence .` and notice it finds a line in a
   file you might have forgotten you moved.

## Quick Quiz

1. Why are plain-text files a good default for notes and code?
   - a) They are encrypted by default
   - b) Any tool can read, search, and compare them
   - c) They take up no disk space
   - d) They can only be opened by one program, which keeps them safe

   **Answer:** b) Any tool can read, search, and compare them — plain text has no lock-in:
   `grep` can search it, `diff` can compare it, and git can version it. Formats only one
   app can open give you none of that.

2. Which command prints a file's contents straight into the terminal?
   - a) `cat`
   - b) `mkdir`
   - c) `grep`
   - d) `mv`

   **Answer:** a) `cat` — it writes the whole file to the terminal. `grep` prints only the
   lines that match a search, and the other two do not read files at all.

3. You remember a file mentions "harbor" but not what the file is called. What finds it?
   - a) `ls -la`, then reading every name
   - b) `mv harbor`
   - c) `touch harbor.txt`
   - d) `grep -r harbor .`

   **Answer:** d) `grep -r harbor .` — a recursive grep searches contents rather than
   names, so it finds the word wherever it lives. A listing of names can never see inside
   the files.

## Homework Assignment

### Shipshape

**Objective:** Turn a messy folder into one a stranger could navigate, using only shell
commands.

Pick a folder of your own that has grown untidy — or scatter a dozen throwaway files in a
fresh one and practise on that.

- [ ] Subdirectories created with `mkdir`, named so their purpose is obvious
- [ ] Every loose file moved into a fitting subdirectory with `mv`
- [ ] At least one file renamed so its name says what it contains
- [ ] One `grep` search that finds a file by a word written inside it
- [ ] A listing of the finished tree, captured from `ls` or `find`

**Stretch Goals:**
- [ ] A `README.txt` at the top of the folder describing the layout, so the next person
  doesn't need to ask

**Submission:** Tell your tutor when it's ready and share the listing and the commands you
used to get there.

## Next Up

Your files are organised. Next you'll make their history permanent — git remembers every
version of everything, forever.
