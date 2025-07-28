import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Read the CSV file
df = pd.read_csv('process_data.csv')

# Check if 'Timestamp' has any spaces or casing issues
df.columns = df.columns.str.strip()  # Remove any extra spaces in the column names

# Convert the 'Timestamp' column to datetime
df['Timestamp'] = pd.to_datetime(df['Timestamp'])

# Plot 'Peak Value' against 'Timestamp'
plt.plot(df['Timestamp'], df['Peak Value'], label='Peak Value')

# Add labels and title
plt.xlabel('Time')
plt.ylabel('Peak Value')
plt.title('Time vs Peak Value')

# Rotate date labels for better visibility
plt.xticks(rotation=45)

# Format the x-axis to show datetime more clearly
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))

# Optionally set the tick frequency for the x-axis (this may need tweaking)
plt.gca().xaxis.set_major_locator(mdates.MinuteLocator(interval=1))  # Adjust interval as needed

# Show grid for better visualization
plt.grid(True)

# Adjust layout to avoid clipping
plt.tight_layout()

# Save the plot as a PNG file (you can specify the path)
plt.savefig('/home/pi/Documents/knockoff/plot.png')  # Modify the path to save where needed

# Optionally, you can use plt.show() if you are running the script with a GUI
# plt.show()  # Uncomment if you want to display the plot on a GUI
