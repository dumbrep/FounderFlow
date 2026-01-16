from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scope for Forms API
SCOPES = ["https://www.googleapis.com/auth/forms.body"]

def main():
    # Authenticate user
    flow = InstalledAppFlow.from_client_secrets_file(
        "credentials.json", SCOPES
    )
    creds = flow.run_local_server(port=0)

    # Build the Forms API service
    service = build("forms", "v1", credentials=creds)

    # Create a new form
    new_form = {
        "info": {
            "title": "Python Created Form",
            "documentTitle": "Python Form Example",
        }
    }

    # Create the form
    form = service.forms().create(body=new_form).execute()
    print(f"Form created: {form['responderUri']}")

    # Add a question
    update = {
  "requests": [
    {
      "createItem": {
        "item": {
          "title": "Full Name",
          "questionItem": {
            "question": {
              "required": True,
              "textQuestion": {}
            }
          }
        },
        "location": {"index": 0}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Email Address",
          "questionItem": {
            "question": {
              "required": True,
              "textQuestion": {
                "paragraph": False
              }
            }
          }
        },
        "location": {"index": 1}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Contact Number",
          "questionItem": {
            "question": {
              "required": True,
              "textQuestion": {}
            }
          }
        },
        "location": {"index": 2}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Applying for Job Role",
          "questionItem": {
            "question": {
              "required": True,
              "textQuestion": {}
            }
          }
        },
        "location": {"index": 3}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Years of Experience",
          "questionItem": {
            "question": {
              "required": True,
              "choiceQuestion": {
                "type": "RADIO",
                "options": [
                  {"value": "Fresher"},
                  {"value": "1–2 years"},
                  {"value": "3–5 years"},
                  {"value": "5+ years"}
                ],
                "shuffle": False
              }
            }
          }
        },
        "location": {"index": 4}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Technical Skills / Tools Known",
          "questionItem": {
            "question": {
              "required": True,
              "textQuestion": {
                "paragraph": True
              }
            }
          }
        },
        "location": {"index": 5}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Educational Qualification",
          "questionItem": {
            "question": {
              "required": True,
              "textQuestion": {}
            }
          }
        },
        "location": {"index": 6}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Upload Resume (Drive/LinkedIn/GitHub link)",
          "questionItem": {
            "question": {
              "required": True,
              "textQuestion": {}
            }
          }
        },
        "location": {"index": 7}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Why do you want to join our company?",
          "questionItem": {
            "question": {
              "required": True,
              "textQuestion": {
                "paragraph": True
              }
            }
          }
        },
        "location": {"index": 8}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Notice Period",
          "questionItem": {
            "question": {
              "required": True,
              "choiceQuestion": {
                "type": "RADIO",
                "options": [
                  {"value": "Immediate Joiner"},
                  {"value": "15 Days"},
                  {"value": "30 Days"},
                  {"value": "More than 30 Days"}
                ],
                "shuffle": False
              }
            }
          }
        },
        "location": {"index": 9}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Expected CTC (in LPA)",
          "questionItem": {
            "question": {
              "required": False,
              "textQuestion": {}
            }
          }
        },
        "location": {"index": 10}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Current Location",
          "questionItem": {
            "question": {
              "required": False,
              "textQuestion": {}
            }
          }
        },
        "location": {"index": 11}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "Are you willing to relocate?",
          "questionItem": {
            "question": {
              "required": True,
              "choiceQuestion": {
                "type": "RADIO",
                "options": [
                  {"value": "Yes"},
                  {"value": "No"}
                ],
                "shuffle": False
              }
            }
          }
        },
        "location": {"index": 12}
      }
    },
    {
      "createItem": {
        "item": {
          "title": "LinkedIn / Portfolio URL (if any)",
          "questionItem": {
            "question": {
              "required": False,
              "textQuestion": {}
            }
          }
        },
        "location": {"index": 13}
      }
    }
  ]
}

    # Update form with the question
    service.forms().batchUpdate(formId=form["formId"], body=update).execute()
    print("Question added successfully!")

if __name__ == "__main__":
    main()
