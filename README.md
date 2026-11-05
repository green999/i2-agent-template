# i2 agent template

Golden template for LangGraph agents on self-hosted LangSmith (Azure Government). A new agent gets caller
authentication (LangSmith API key or Entra), MCP tool loading (direct or through the APIM gateway with
On-Behalf-Of tokens), a step limit, a prompt file, pinned packages, evals, tests and the image build.

## Make a new agent

```powershell
pip install copier
copier copy --trust --vcs-ref v0.2.3 git+https://dev.azure.com/<org>/<project>/_git/i2-agent-template <agent-name>
```

Write the URL with `git+` in front. Azure DevOps URLs do not end in `.git`, and without the prefix copier treats
the URL as a local folder ("Local template must be a directory"). GitHub: `git+https://github.com/<org>/i2-agent-template.git`.
Git asks for your sign-in the first time (Git Credential Manager on Windows).

Then follow the generated project's README. The identity library comes from the
[i2-platform-auth](../i2-platform-auth) repo: `pip install -e <i2-platform-auth folder>` (a path, never a bare name).

## Take a newer template version, change the template

Same as the MCP template: `copier update --trust --vcs-ref <tag>` in a clean git project; template changes on a
branch, `python check_template.py`, pull request, CHANGELOG entry, tag.
