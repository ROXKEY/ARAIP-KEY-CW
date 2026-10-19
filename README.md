# KEY ARAIP Project

Repo for my Applied Robotics and AI Project (ARAIP) module. I use Git and GitHub to back up my work and track changes, and Trello to plan tasks.

Trello board: https://trello.com/b/u4sQMrFD/key-araip-project

## Quick guide to the Git commands

### 1. Clone (get the repo on your computer)

```bash
git clone https://github.com/<my-username>/<repo-name>.git
cd <repo-name>
```

### 2. Edit, then check what changed

Open a file, change it and save. Then:

```bash
git status      # shows which files are modified
git diff        # shows exactly what changed
```

### 3. Add (stage the change)

```bash
git add <file>      # one file
git add .           # everything that changed
```

### 4. Commit (save a snapshot locally)

```bash
git commit -m "Short message about what changed"
```

### 5. Push (upload to GitHub)

```bash
git push
```

Refresh the repo on GitHub to see the new commit. To look at history from the terminal, run `git log --oneline`.

### Add vs Commit vs Push

- **add** picks the changes for the next save
- **commit** saves them to my local history
- **push** sends them to GitHub

### 6. Branch (work without touching main)

```bash
git switch -c feature/short-name              # create and switch to a branch
git add . && git commit -m "Work on feature"  # commit on the branch
git push -u origin feature/short-name         # push the branch
```

Then open a pull request on GitHub and merge it into `main`. Afterwards:

```bash
git switch main
git pull
```

## What I've done so far

- Created the GitHub repo and pushed the first commit (`KEY.txt`)
- Wrote this README
- Set up the Trello board (To Do, Doing, Done) and invited the lecturer
- Practised add, commit, push, clone and branching

## Screenshots

(I will add the commit history, a merged pull request and the Trello board here.)
