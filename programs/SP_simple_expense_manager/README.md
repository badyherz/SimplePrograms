Simple Programs: Simple Expense Manager powered by Python

This README is just for additional information about the program.
There are some nice features for a better user experience, but some are missing or need a bit of manual work.
The program folder can be found in your local Documents folder under your user.

**Creating your own language file:**
The program comes with a default language creation for English, but separate english.json and german.json files are also available.
If you want to create your own translation, just copy, for example, english.json and rename it to yourlanguage.json, then edit/translate all the strings from English to your language.
DO NOT edit/translate the keys on the left, or the program will not accept your file.
Also DO NOT delete the commas behind the translation, or else all translations will break.
Then just put your language.json file into the language folder of the program. Restart, and it should just show up under Settings--Language. Select and restart the program.

**Adding years after the current year:**
This has to be done manually, but I provided a template file. (You can also edit the file created by the program on first start)
In there, you can see the structure of the file. This is very unforgiving, and even one missing comma or bracket will break the data read.
But do not worry, if you made a mistake, the program will not start and will just throw an error.
Change the yyyy to whatever year you want to add and fill in the months (OR NOT: after adding the year, this should show up in the program, where you can then fill in the months)
You can add all the years you want; the order does not matter technically.
DO NOT delete single months in the file; this will break the program. (Since I did not add a fallback for that)
You DON'T need to add the current year. The program will always add the current year automatically on start.
