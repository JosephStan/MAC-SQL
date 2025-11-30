#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Error Distribution Visualization for MAC-SQL

This script generates pie charts showing error distribution similar to 
Figure 6 in the MAC-SQL paper. It creates visualizations for both 
BIRD and Spider datasets.

Usage:
    python generate_error_charts.py --bird_analysis ./outputs/bird_subset_8/error_analysis.json \
                                    --spider_analysis ./outputs/spider/error_analysis.json \
                                    --output_dir ./outputs/charts/
"""

import os
import json
import argparse
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from typing import Dict, List, Optional

# Error types as defined in the paper
ERROR_TYPES = [
    "Gold Error",
    "Database Misunderstand",
    "Semantic Correct", 
    "Question Misunderstand",
    "Evidence Misunderstand",
    "Dirty Database Values",
    "Schema Linking Error",
    "Other"
]

# Color scheme matching the paper's style (warm colors for major errors)
COLORS = {
    "Gold Error": "#FFD700",            # Gold
    "Database Misunderstand": "#FF8C00", # Dark Orange
    "Semantic Correct": "#32CD32",       # Lime Green
    "Question Misunderstand": "#87CEEB", # Sky Blue
    "Evidence Misunderstand": "#DDA0DD", # Plum
    "Dirty Database Values": "#FF6B6B",  # Light Red/Coral
    "Schema Linking Error": "#4ECDC4",   # Teal
    "Other": "#95A5A6"                   # Gray
}


def load_error_analysis(path: str) -> Optional[Dict]:
    """Load error analysis JSON file."""
    if not os.path.exists(path):
        print(f"Warning: File not found: {path}")
        return None
    
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_pie_chart(error_distribution: Dict, dataset_name: str, 
                     ax: plt.Axes, show_legend: bool = False) -> None:
    """
    Create a pie chart for error distribution.
    
    Args:
        error_distribution: Dictionary with error type -> {count, percentage}
        dataset_name: Name of the dataset (BIRD or Spider)
        ax: Matplotlib axes object
        show_legend: Whether to show legend
    """
    labels = []
    sizes = []
    colors = []
    
    # Sort by percentage for consistent ordering
    sorted_errors = sorted(
        [(et, error_distribution.get(et, {'percentage': 0})) 
         for et in ERROR_TYPES],
        key=lambda x: -x[1].get('percentage', 0)
    )
    
    for error_type, info in sorted_errors:
        percentage = info.get('percentage', 0)
        if percentage > 0:
            labels.append(error_type)
            sizes.append(percentage)
            colors.append(COLORS.get(error_type, '#95A5A6'))
    
    if not sizes:
        ax.text(0.5, 0.5, 'No Error Data', ha='center', va='center', fontsize=14)
        ax.set_title(dataset_name, fontsize=16, fontweight='bold')
        return
    
    # Create pie chart
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=None,
        autopct=lambda pct: f'{pct:.0f}%' if pct >= 3 else '',
        startangle=90,
        colors=colors,
        pctdistance=0.75,
        wedgeprops=dict(width=0.6, edgecolor='white', linewidth=1)
    )
    
    # Style the percentage labels
    for autotext in autotexts:
        autotext.set_fontsize(10)
        autotext.set_fontweight('bold')
        autotext.set_color('black')
    
    # Add title
    ax.set_title(dataset_name, fontsize=16, fontweight='bold', pad=15)


def create_comparison_chart(bird_data: Optional[Dict], spider_data: Optional[Dict],
                           output_path: str) -> None:
    """
    Create a side-by-side comparison chart of BIRD and Spider error distributions.
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    
    # BIRD chart
    if bird_data and 'error_distribution' in bird_data:
        create_pie_chart(bird_data['error_distribution'], 'BIRD', axes[0])
    else:
        axes[0].text(0.5, 0.5, 'BIRD Data Not Available', 
                     ha='center', va='center', fontsize=12)
        axes[0].set_title('BIRD', fontsize=16, fontweight='bold')
    
    # Spider chart  
    if spider_data and 'error_distribution' in spider_data:
        create_pie_chart(spider_data['error_distribution'], 'Spider', axes[1])
    else:
        axes[1].text(0.5, 0.5, 'Spider Data Not Available',
                     ha='center', va='center', fontsize=12)
        axes[1].set_title('Spider', fontsize=16, fontweight='bold')
    
    # Create shared legend
    legend_patches = [
        mpatches.Patch(color=COLORS[et], label=et)
        for et in ERROR_TYPES
    ]
    
    fig.legend(
        handles=legend_patches,
        loc='lower center',
        bbox_to_anchor=(0.5, -0.05),
        ncol=4,
        fontsize=10,
        frameon=True,
        fancybox=True,
        shadow=True
    )
    
    # Add main title
    fig.suptitle('Error Type Distribution: MAC-SQL Framework', 
                 fontsize=18, fontweight='bold', y=1.02)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()
    
    print(f"Saved comparison chart to: {output_path}")


def create_single_chart(error_data: Dict, dataset_name: str, 
                        output_path: str) -> None:
    """Create a single pie chart for one dataset."""
    fig, ax = plt.subplots(figsize=(10, 8))
    
    if 'error_distribution' in error_data:
        create_pie_chart(error_data['error_distribution'], dataset_name, ax)
    else:
        ax.text(0.5, 0.5, 'Error Data Not Available',
                ha='center', va='center', fontsize=12)
        ax.set_title(dataset_name, fontsize=16, fontweight='bold')
    
    # Add legend
    legend_patches = [
        mpatches.Patch(color=COLORS[et], label=et)
        for et in ERROR_TYPES
        if error_data.get('error_distribution', {}).get(et, {}).get('percentage', 0) > 0
    ]
    
    ax.legend(
        handles=legend_patches,
        loc='center left',
        bbox_to_anchor=(1, 0.5),
        fontsize=10,
        frameon=True
    )
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    
    print(f"Saved chart to: {output_path}")


def create_summary_table(bird_data: Optional[Dict], spider_data: Optional[Dict],
                         output_path: str) -> None:
    """Create a summary table of error distributions."""
    
    summary = []
    summary.append("="*80)
    summary.append("ERROR DISTRIBUTION COMPARISON: BIRD vs Spider")
    summary.append("="*80)
    summary.append("")
    summary.append(f"{'Error Type':<30} {'BIRD %':<15} {'Spider %':<15}")
    summary.append("-"*60)
    
    for error_type in ERROR_TYPES:
        bird_pct = "N/A"
        spider_pct = "N/A"
        
        if bird_data and 'error_distribution' in bird_data:
            bird_info = bird_data['error_distribution'].get(error_type, {})
            bird_pct = f"{bird_info.get('percentage', 0):.1f}%"
        
        if spider_data and 'error_distribution' in spider_data:
            spider_info = spider_data['error_distribution'].get(error_type, {})
            spider_pct = f"{spider_info.get('percentage', 0):.1f}%"
        
        summary.append(f"{error_type:<30} {bird_pct:<15} {spider_pct:<15}")
    
    summary.append("-"*60)
    
    # Add totals
    if bird_data:
        summary.append(f"\nBIRD Total Errors: {bird_data.get('total_errors', 'N/A')}")
        summary.append(f"BIRD Accuracy: {bird_data.get('accuracy', 'N/A')}%")
    
    if spider_data:
        summary.append(f"\nSpider Total Errors: {spider_data.get('total_errors', 'N/A')}")
        summary.append(f"Spider Accuracy: {spider_data.get('accuracy', 'N/A')}%")
    
    summary.append("="*80)
    
    # Print and save
    summary_text = "\n".join(summary)
    print(summary_text)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(summary_text)
    
    print(f"\nSaved summary to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Generate Error Distribution Charts')
    parser.add_argument('--bird_analysis', type=str, default=None,
                        help='Path to BIRD error analysis JSON')
    parser.add_argument('--spider_analysis', type=str, default=None,
                        help='Path to Spider error analysis JSON')
    parser.add_argument('--output_dir', type=str, default='./outputs/charts/',
                        help='Directory to save charts')
    parser.add_argument('--create_comparison', action='store_true',
                        help='Create side-by-side comparison chart')
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Load error analysis data
    bird_data = None
    spider_data = None
    
    if args.bird_analysis:
        bird_data = load_error_analysis(args.bird_analysis)
        if bird_data:
            print(f"Loaded BIRD error analysis: {args.bird_analysis}")
    
    if args.spider_analysis:
        spider_data = load_error_analysis(args.spider_analysis)
        if spider_data:
            print(f"Loaded Spider error analysis: {args.spider_analysis}")
    
    # Generate charts
    if bird_data:
        bird_chart_path = os.path.join(args.output_dir, 'bird_error_distribution.png')
        create_single_chart(bird_data, 'BIRD', bird_chart_path)
    
    if spider_data:
        spider_chart_path = os.path.join(args.output_dir, 'spider_error_distribution.png')
        create_single_chart(spider_data, 'Spider', spider_chart_path)
    
    if args.create_comparison or (bird_data and spider_data):
        comparison_path = os.path.join(args.output_dir, 'error_distribution_comparison.png')
        create_comparison_chart(bird_data, spider_data, comparison_path)
    
    # Generate summary table
    summary_path = os.path.join(args.output_dir, 'error_distribution_summary.txt')
    create_summary_table(bird_data, spider_data, summary_path)
    
    print("\nChart generation complete!")


if __name__ == '__main__':
    main()
