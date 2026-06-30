# UX Analysis & Improvements: Migration Dashboard

## 1. Overview
This document outlines the UX/UI improvements for the Migration Dashboard, focusing on better visualizing overall progress, differentiating active tasks (download vs. upload), and refining the activity list.

## 2. Top Section: Overall Progress & ETA
- **Global Progress Bar**: A prominent progress bar at the top of the dashboard displaying the total amount of data migrated out of the total data size (e.g., in GB or TB).
- **Percentage Indicator**: Clear percentage value showing overall completion.
- **Estimated Time of Arrival (ETA)**: A dynamic estimate of how long it will take to complete the migration, based on current transfer speeds.

## 3. Current Activity Section (Bottom)
The section showing active transfers will be moved **below** the "Recent Activity" list. It will display ongoing tasks as separate rows:
- **Download Row**: 
  - Dedicated download icon.
  - Active progress bar with a specific color (e.g., Blue).
  - Shows file name, size, and download progress.
- **Upload Row**: 
  - Dedicated upload icon.
  - Specific color scheme (e.g., Purple or Orange).
  - The row remains static in terms of file name and total size (matches the file currently being downloaded or just finished downloading).
  - *Note: Needs clarification on whether to show upload progress or just a status indicator.*

## 4. Recent Activity List
- **Completed Items**: Instead of just text, completed files will feature a visual **Green Checkmark** icon (`✓`) to quickly communicate success.

## 5. Further Ideas & Enhancements
- **Dynamic Speed Indicator**: Display the current average transfer speed (MB/s) next to the ETA in the Top Section to give context to the time estimate.
- **Moving Average for ETA**: Calculate ETA using a moving average of the transfer speed over the last 5-10 minutes to avoid erratic ETA jumps.
- **Size Unit Toggle**: A simple toggle to switch between viewing total sizes in MB, GB, or TB.
- **Upload Progress**: Investigate if chunked upload progress can be reliably shown for the Google Drive upload phase to provide a matching progress bar to the download phase.
