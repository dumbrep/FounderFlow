import asyncio
from generateLinkedin_post import generate_linkedin_post
from linkedin_post import post_to_linkedin

async def main():
    user_prompt = input("Enter your LinkedIn post prompt: ")

    # Step 1: Generate post using AI
    post_content = generate_linkedin_post(user_prompt)

    while True:
        print("\nGenerated Post Preview:\n")
        print("-----------------------------------")
        print(post_content)
        print("-----------------------------------")

        print("\nWhat would you like to do?")
        print("1. Post to LinkedIn")
        print("2. Edit this post manually")
        print("3. Regenerate post with new prompt")
        print("4. Cancel")

        choice = input("Enter choice (1/2/3/4): ")

        # ✅ Final confirmation before posting
        if choice == "1":
            confirm = input("Are you sure you want to post this? (yes/no): ")

            if confirm.lower() == "yes":
                response = await post_to_linkedin(post_content)
                print("\n✅ Posted Successfully:\n", response)
                break
            else:
                print("Posting cancelled. You can edit or regenerate.")

        # ✅ Manual editing (No regeneration)
        elif choice == "2":
            print("\nEnter your edited version below:")
            post_content = input()

        # ✅ Regenerate new content
        elif choice == "3":
            new_prompt = input("Enter new LinkedIn post prompt: ")
            post_content = generate_linkedin_post(new_prompt)

        # ✅ Cancel completely
        elif choice == "4":
            print("\n❌ Posting cancelled.")
            break

        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    asyncio.run(main())
