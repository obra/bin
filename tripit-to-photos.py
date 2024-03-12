import json
from datetime import datetime
import osxphotos

# Number of albums per page
num_albums = 80
# Page number to display
page = 3
# Folder name to store albums
folder_name = "Trips"

# Load trips data from a JSON file
print("Loading trips.json...")
with open('trips.json') as json_file:
    trips = json.load(json_file)

# Extract all trips from the loaded JSON data
all_trips = trips['Trip']

# Reverse the order of trips for latest first
all_trips.reverse()

# Slice the trips list to get the trips for the current page
trips_paged = all_trips[(page-1)*num_albums:page*num_albums]

# Display the number of trips found and the number of trips on the current page
print(f"Found {len(all_trips)} trips. {len(trips_paged)} trips on page {page}.")
# Calculate and display the total number of pages
print(f"Total pages: {len(all_trips)/num_albums}")

# Initialize the PhotosDB object to interact with the photos database
print("Initializing PhotosDB object...")
photosdb = osxphotos.PhotosDB()

# Counter for the number of processed trips
count = 0
print(f"Found {len(trips_paged)} trips.")
# Iterate over each trip in the current page
for trip in trips_paged:

    # Create an album name based on trip's display name and date range
    album_name = f"{trip['display_name']} - {trip['start_date']} to {trip['end_date']}"
    print(f"[{count}] Initializing album... {album_name}")
    
    # Convert the start and end dates from string to datetime objects
    start_date = datetime.strptime(trip['start_date'], "%Y-%m-%d")
    end_date = datetime.strptime(trip['end_date'], "%Y-%m-%d")
    print(f"[{count}] Searching for photos between {start_date} and {end_date}...")
    # Retrieve photos from the database that fall within the date range
    photos = photosdb.photos(from_date=start_date, to_date=end_date)
    print(f"[{count}] Found {len(photos)} photos between {start_date} and {end_date}.")

    # If photos are found, create an album and add the photos to it
    if len(photos) > 0:
        album = osxphotos.PhotosAlbum(f"{folder_name}/{album_name}", split_folder="/")
        print(f"[{count}] Found {len(photos)} matching photos. Adding to album '{album_name}'...")
        album.add_list(photos)
    # Increment the trip counter
    count += 1
